"""Offline LaTeX to MathML (HTML5) and Native Word OMML (`<m:oMath>`) XML Converter.

Transforms inline (`$...$`) and display (`$$...$$`) LaTeX equations into:
1. Standard W3C MathML (`<math>...</math>`) via `latex2mathml` for HTML5 & PDF rendering.
2. Native Office Math Markup Language (`<m:oMath>` / `<m:oMathPara>`) OpenXML trees for
   Microsoft Word `.docx` documents (`Alt + =` equation editor compatible) with zero external
   XSLT binary dependencies.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import List, Optional

import latex2mathml.converter
from lxml import etree

OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"m": OMML_NS, "w": WORD_NS}

_MATH_TOKEN_RE = re.compile(r"(\$\$.+?\$\$|(?<!\$)\$(?!\$).+?(?<!\$)\$(?!\$))", re.DOTALL)


def _m_tag(local_name: str) -> str:
    return f"{{{OMML_NS}}}{local_name}"


def _w_tag(local_name: str) -> str:
    return f"{{{WORD_NS}}}{local_name}"


def _local_name(element: etree._Element) -> str:
    tag = element.tag
    if isinstance(tag, str) and "}" in tag:
        return tag.split("}", 1)[1]
    return str(tag)


@dataclass
class TextOrMathSegment:
    """Segment of a rich text line split into plain text or LaTeX math."""

    is_math: bool
    is_display_math: bool
    content: str


class MathConverter:
    """Offline converter from LaTeX to MathML and Microsoft Word OMML (`<m:oMath>`)."""

    @staticmethod
    def latex_to_mathml(latex_expr: str, display: str = "inline") -> str:
        """Convert a single LaTeX equation string into a MathML XML string."""
        cleaned = latex_expr.strip()
        if cleaned.startswith("$$") and cleaned.endswith("$$"):
            cleaned = cleaned[2:-2].strip()
            display = "block"
        elif cleaned.startswith("$") and cleaned.endswith("$"):
            cleaned = cleaned[1:-1].strip()

        return latex2mathml.converter.convert(cleaned, display=display)

    @staticmethod
    def latex_to_omml_element(latex_expr: str, display_block: bool = False) -> etree._Element:
        """Convert a LaTeX equation into a native Word `<m:oMath>` (or `<m:oMathPara>`) lxml Element."""
        cleaned = html.unescape(latex_expr.strip())
        if cleaned.startswith("$$") and cleaned.endswith("$$"):
            cleaned = cleaned[2:-2].strip()
            display_block = True
        elif cleaned.startswith("$") and cleaned.endswith("$"):
            cleaned = cleaned[1:-1].strip()

        omath = etree.Element(_m_tag("oMath"), nsmap=NSMAP)
        try:
            mathml_str = latex2mathml.converter.convert(cleaned, display="inline")
            mathml_root = etree.fromstring(mathml_str.encode("utf-8"))
            MathConverter._translate_mathml_children_to_omml(mathml_root, omath)
        except Exception:
            # Fallback: emit a valid `<m:r><m:t>` run inside `<m:oMath>`
            MathConverter._append_omml_run(omath, cleaned)

        if display_block:
            para = etree.Element(_m_tag("oMathPara"), nsmap=NSMAP)
            para.append(omath)
            return para
        return omath

    @staticmethod
    def split_text_and_math(raw_text: str) -> List[TextOrMathSegment]:
        """Split a string containing inline `$...$` or block `$$...$$` LaTeX into ordered segments."""
        if "$" not in raw_text:
            return [TextOrMathSegment(is_math=False, is_display_math=False, content=raw_text)]

        parts = _MATH_TOKEN_RE.split(raw_text)
        segments: List[TextOrMathSegment] = []
        for part in parts:
            if not part:
                continue
            if part.startswith("$$") and part.endswith("$$") and len(part) > 4:
                segments.append(
                    TextOrMathSegment(
                        is_math=True,
                        is_display_math=True,
                        content=part[2:-2].strip(),
                    )
                )
            elif part.startswith("$") and part.endswith("$") and len(part) > 2:
                segments.append(
                    TextOrMathSegment(
                        is_math=True,
                        is_display_math=False,
                        content=part[1:-1].strip(),
                    )
                )
            else:
                segments.append(
                    TextOrMathSegment(
                        is_math=False,
                        is_display_math=False,
                        content=part,
                    )
                )
        return segments

    @staticmethod
    def _append_omml_run(parent_omml: etree._Element, text: str, normal_text: bool = False) -> None:
        if not text:
            return
        r_el = etree.SubElement(parent_omml, _m_tag("r"))
        if normal_text:
            rpr = etree.SubElement(r_el, _m_tag("rPr"))
            nor = etree.SubElement(rpr, _m_tag("nor"))
            nor.set(_m_tag("val"), "1")
        t_el = etree.SubElement(r_el, _m_tag("t"))
        t_el.text = text

    @staticmethod
    def _translate_mathml_children_to_omml(
        mml_parent: etree._Element,
        omml_target: etree._Element,
    ) -> None:
        for child in mml_parent:
            MathConverter._translate_mathml_node(child, omml_target)

    @staticmethod
    def _translate_mathml_node(
        mml_node: etree._Element,
        omml_target: etree._Element,
    ) -> None:
        lname = _local_name(mml_node)
        text_val = "".join(mml_node.itertext()).strip()

        # 1. Atomic leaf tokens: mi, mn, mo, mtext
        if lname in ("mi", "mn", "mo", "mtext"):
            MathConverter._append_omml_run(
                omml_target,
                text_val,
                normal_text=(lname == "mtext"),
            )
            return

        # 2. Grouping containers: math, mrow, mpadded, mstyle, semantics
        if lname in ("math", "mrow", "mpadded", "mstyle", "semantics"):
            MathConverter._translate_mathml_children_to_omml(mml_node, omml_target)
            return

        children = list(mml_node)

        # 3. Fraction: <mfrac> -> <m:f><m:num>...</m:num><m:den>...</m:den></m:f>
        if lname == "mfrac" and len(children) >= 2:
            f_el = etree.SubElement(omml_target, _m_tag("f"))
            num_el = etree.SubElement(f_el, _m_tag("num"))
            den_el = etree.SubElement(f_el, _m_tag("den"))
            MathConverter._translate_mathml_node(children[0], num_el)
            MathConverter._translate_mathml_node(children[1], den_el)
            return

        # 4. Superscript: <msup> -> <m:sSup><m:e>...</m:e><m:sup>...</m:sup></m:sSup>
        if lname == "msup" and len(children) >= 2:
            ssup = etree.SubElement(omml_target, _m_tag("sSup"))
            e_el = etree.SubElement(ssup, _m_tag("e"))
            sup_el = etree.SubElement(ssup, _m_tag("sup"))
            MathConverter._translate_mathml_node(children[0], e_el)
            MathConverter._translate_mathml_node(children[1], sup_el)
            return

        # 5. Subscript: <msub> -> <m:sSub><m:e>...</m:e><m:sub>...</m:sub></m:sSub>
        if lname == "msub" and len(children) >= 2:
            ssub = etree.SubElement(omml_target, _m_tag("sSub"))
            e_el = etree.SubElement(ssub, _m_tag("e"))
            sub_el = etree.SubElement(ssub, _m_tag("sub"))
            MathConverter._translate_mathml_node(children[0], e_el)
            MathConverter._translate_mathml_node(children[1], sub_el)
            return

        # 6. Sub-Superscript: <msubsup> -> <m:sSubSup>
        if lname == "msubsup" and len(children) >= 3:
            ssubsup = etree.SubElement(omml_target, _m_tag("sSubSup"))
            e_el = etree.SubElement(ssubsup, _m_tag("e"))
            sub_el = etree.SubElement(ssubsup, _m_tag("sub"))
            sup_el = etree.SubElement(ssubsup, _m_tag("sup"))
            MathConverter._translate_mathml_node(children[0], e_el)
            MathConverter._translate_mathml_node(children[1], sub_el)
            MathConverter._translate_mathml_node(children[2], sup_el)
            return

        # 7. Square Root: <msqrt> -> <m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>...</m:e></m:rad>
        if lname == "msqrt":
            rad = etree.SubElement(omml_target, _m_tag("rad"))
            rad_pr = etree.SubElement(rad, _m_tag("radPr"))
            deg_hide = etree.SubElement(rad_pr, _m_tag("degHide"))
            deg_hide.set(_m_tag("val"), "1")
            etree.SubElement(rad, _m_tag("deg"))
            e_el = etree.SubElement(rad, _m_tag("e"))
            MathConverter._translate_mathml_children_to_omml(mml_node, e_el)
            return

        # 8. N-th Root: <mroot> -> <m:rad><m:deg>...</m:deg><m:e>...</m:e></m:rad>
        if lname == "mroot" and len(children) >= 2:
            rad = etree.SubElement(omml_target, _m_tag("rad"))
            deg_el = etree.SubElement(rad, _m_tag("deg"))
            e_el = etree.SubElement(rad, _m_tag("e"))
            MathConverter._translate_mathml_node(children[1], deg_el)
            MathConverter._translate_mathml_node(children[0], e_el)
            return

        # 9. Under/Over/UnderOver (Summation, Integral limits, Hats/Bars)
        if lname in ("munderover", "munder", "mover") and len(children) >= 2:
            if lname == "munderover" and len(children) >= 3:
                nary_or_lim = etree.SubElement(omml_target, _m_tag("sSubSup"))
                e_el = etree.SubElement(nary_or_lim, _m_tag("e"))
                sub_el = etree.SubElement(nary_or_lim, _m_tag("sub"))
                sup_el = etree.SubElement(nary_or_lim, _m_tag("sup"))
                MathConverter._translate_mathml_node(children[0], e_el)
                MathConverter._translate_mathml_node(children[1], sub_el)
                MathConverter._translate_mathml_node(children[2], sup_el)
            elif lname == "munder":
                lim_low = etree.SubElement(omml_target, _m_tag("limLow"))
                e_el = etree.SubElement(lim_low, _m_tag("e"))
                lim_el = etree.SubElement(lim_low, _m_tag("lim"))
                MathConverter._translate_mathml_node(children[0], e_el)
                MathConverter._translate_mathml_node(children[1], lim_el)
            else:
                lim_upp = etree.SubElement(omml_target, _m_tag("limUpp"))
                e_el = etree.SubElement(lim_upp, _m_tag("e"))
                lim_el = etree.SubElement(lim_upp, _m_tag("lim"))
                MathConverter._translate_mathml_node(children[0], e_el)
                MathConverter._translate_mathml_node(children[1], lim_el)
            return

        # 10. Matrix / Table: <mtable> -> <m:m>
        if lname == "mtable":
            m_el = etree.SubElement(omml_target, _m_tag("m"))
            for row_node in children:
                if _local_name(row_node) == "mtr":
                    mr_el = etree.SubElement(m_el, _m_tag("mr"))
                    for cell_node in row_node:
                        if _local_name(cell_node) == "mtd":
                            e_el = etree.SubElement(mr_el, _m_tag("e"))
                            MathConverter._translate_mathml_children_to_omml(cell_node, e_el)
            return

        # Default fallback for any other MathML node: recurse if children exist else emit run
        if children:
            MathConverter._translate_mathml_children_to_omml(mml_node, omml_target)
        elif text_val:
            MathConverter._append_omml_run(omml_target, text_val)
