"""Hierarchical Numbering Finite State Machine (FSM), Tree Manipulator, and Undo/Redo Command Stack."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.core.models.enums import NumberingStyle
from src.core.models.project_model import ProjectState
from src.core.models.question_model import QuestionNode
from src.core.models.section_model import Section


def int_to_roman(n: int, uppercase: bool = True) -> str:
    """Convert a positive integer (1..3999) to Roman numerals."""
    if n <= 0:
        return str(n)
    val_map = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    result: List[str] = []
    remaining = n
    for value, numeral in val_map:
        while remaining >= value:
            result.append(numeral)
            remaining -= value
    roman = "".join(result)
    return roman if uppercase else roman.lower()


def int_to_alpha(n: int, uppercase: bool = True) -> str:
    """Convert a 1-based positive integer to alphabetic label (1->A/a, 26->Z/z, 27->AA/aa)."""
    if n <= 0:
        return str(n)
    result = ""
    idx = n - 1
    base = ord("A") if uppercase else ord("a")
    while idx >= 0:
        result = chr(base + (idx % 26)) + result
        idx = (idx // 26) - 1
    return result


def format_index(
    index_1based: int,
    style: NumberingStyle,
    prefix: str = "",
    suffix: str = "",
) -> str:
    """Format a 1-based sibling index according to `style`, `prefix`, and `suffix`."""
    if style == NumberingStyle.NUMERIC or style == NumberingStyle.CUSTOM:
        core = str(index_1based)
    elif style == NumberingStyle.UPPER_ALPHA:
        core = int_to_alpha(index_1based, uppercase=True)
    elif style == NumberingStyle.LOWER_ALPHA:
        core = int_to_alpha(index_1based, uppercase=False)
    elif style == NumberingStyle.UPPER_ROMAN:
        core = int_to_roman(index_1based, uppercase=True)
    elif style == NumberingStyle.LOWER_ROMAN:
        core = int_to_roman(index_1based, uppercase=False)
    else:
        core = str(index_1based)
    return f"{prefix}{core}{suffix}"


# Default progression of child numbering styles by depth if not explicitly customized
DEFAULT_DEPTH_STYLES: Tuple[NumberingStyle, ...] = (
    NumberingStyle.NUMERIC,      # Depth 0 (Top-level Question: 1., 2., 3. or Q1., Q2.)
    NumberingStyle.LOWER_ALPHA,  # Depth 1 (Minor Question: (a), (b), (c))
    NumberingStyle.LOWER_ROMAN,  # Depth 2 (Subquestion: (i), (ii), (iii))
    NumberingStyle.NUMERIC,      # Depth 3 (Further Subquestion: (1), (2), (3))
    NumberingStyle.UPPER_ALPHA,  # Depth 4+
)


class NumberingFSM:
    """Recursive Depth-First Search (DFS) numbering resolver for ProjectState ASTs."""

    @staticmethod
    def resolve_project(project: ProjectState) -> Dict[str, str]:
        """Resolve and assign `resolved_number` on every QuestionNode in `project`.

        Returns a mapping of `{question_id: resolved_number}`.
        Manual `numbering_override` strings are honored on the specific node without
        disrupting the sequential sibling counter for subsequent siblings.
        """
        resolved_map: Dict[str, str] = {}
        running_top_counter = 0

        for sec_idx, section in enumerate(project.sections):
            if sec_idx == 0 or not section.continue_numbering_from_previous:
                running_top_counter = 0

            for q in section.questions:
                running_top_counter += 1
                if q.numbering_override is not None and q.numbering_override.strip() != "":
                    top_label = q.numbering_override.strip()
                else:
                    top_label = format_index(
                        running_top_counter,
                        section.section_numbering_style,
                        prefix=section.question_numbering_prefix,
                        suffix=section.question_numbering_suffix,
                    )
                q.resolved_number = top_label
                resolved_map[q.question_id] = top_label
                NumberingFSM._resolve_children_dfs(q, resolved_map)

        return resolved_map

    @staticmethod
    def _resolve_children_dfs(
        parent: QuestionNode,
        resolved_map: Dict[str, str],
    ) -> None:
        """Recursively resolve child numbering under `parent`."""
        style = parent.child_numbering_style
        prefix = parent.custom_child_prefix
        suffix = parent.custom_child_suffix

        for idx, child in enumerate(parent.children, start=1):
            if child.numbering_override is not None and child.numbering_override.strip() != "":
                label = child.numbering_override.strip()
            else:
                label = format_index(idx, style, prefix=prefix, suffix=suffix)
            child.resolved_number = label
            resolved_map[child.question_id] = label
            NumberingFSM._resolve_children_dfs(child, resolved_map)


@dataclass
class NodeLookupResult:
    """Location metadata for a QuestionNode inside a ProjectState."""

    node: QuestionNode
    section: Section
    parent_node: Optional[QuestionNode]
    sibling_list: List[QuestionNode]
    index_in_siblings: int
    depth: int


class QuestionTreeEngine:
    """Tree manipulation engine supporting add, insert, reorder, reparent, move, duplicate, and delete."""

    @staticmethod
    def find_section(project: ProjectState, section_id: str) -> Optional[Section]:
        """Find a Section by `section_id`."""
        for sec in project.sections:
            if sec.section_id == section_id:
                return sec
        return None

    @staticmethod
    def find_node(project: ProjectState, question_id: str) -> Optional[NodeLookupResult]:
        """Locate a QuestionNode anywhere in `project` and return its structural context."""
        for sec in project.sections:
            res = QuestionTreeEngine._search_in_list(
                sec.questions,
                target_id=question_id,
                section=sec,
                parent_node=None,
                depth=0,
            )
            if res is not None:
                return res
        return None

    @staticmethod
    def _search_in_list(
        siblings: List[QuestionNode],
        target_id: str,
        section: Section,
        parent_node: Optional[QuestionNode],
        depth: int,
    ) -> Optional[NodeLookupResult]:
        for idx, node in enumerate(siblings):
            if node.question_id == target_id:
                return NodeLookupResult(
                    node=node,
                    section=section,
                    parent_node=parent_node,
                    sibling_list=siblings,
                    index_in_siblings=idx,
                    depth=depth,
                )
            sub = QuestionTreeEngine._search_in_list(
                node.children,
                target_id=target_id,
                section=section,
                parent_node=node,
                depth=depth + 1,
            )
            if sub is not None:
                return sub
        return None

    @staticmethod
    def count_descendants(node: QuestionNode) -> int:
        """Return total number of descendant subquestions under `node`."""
        total = len(node.children)
        for ch in node.children:
            total += QuestionTreeEngine.count_descendants(ch)
        return total

    @staticmethod
    def is_descendant_of(candidate_Parent: QuestionNode, target_id: str) -> bool:
        """Return True if `target_id` equals `candidate_Parent.question_id` or is inside its subtree."""
        if candidate_Parent.question_id == target_id:
            return True
        for ch in candidate_Parent.children:
            if QuestionTreeEngine.is_descendant_of(ch, target_id):
                return True
        return False

    @staticmethod
    def _default_child_style_for_depth(depth: int) -> NumberingStyle:
        """Select sensible default child numbering style based on node depth."""
        next_depth = depth + 1
        if next_depth < len(DEFAULT_DEPTH_STYLES):
            return DEFAULT_DEPTH_STYLES[next_depth]
        return NumberingStyle.LOWER_ALPHA

    @staticmethod
    def add_parent_question(
        project: ProjectState,
        question: QuestionNode,
        section_id: Optional[str] = None,
        index: Optional[int] = None,
    ) -> QuestionNode:
        """Add a top-level question to the specified section (or first/default section)."""
        sec = (
            QuestionTreeEngine.find_section(project, section_id)
            if section_id
            else project.sections[0]
        )
        if sec is None:
            raise ValueError(f"Section '{section_id}' not found.")

        question.parent_id = None
        QuestionTreeEngine._propagate_section_id(question, sec.section_id)
        if index is None or index >= len(sec.questions):
            sec.questions.append(question)
        else:
            sec.questions.insert(max(0, index), question)

        NumberingFSM.resolve_project(project)
        return question

    @staticmethod
    def add_child_question(
        project: ProjectState,
        parent_question_id: str,
        child: QuestionNode,
        index: Optional[int] = None,
    ) -> QuestionNode:
        """Add a child subquestion at any depth under `parent_question_id`."""
        lookup = QuestionTreeEngine.find_node(project, parent_question_id)
        if lookup is None:
            raise ValueError(f"Parent question '{parent_question_id}' not found.")

        parent = lookup.node
        child.parent_id = parent.question_id
        QuestionTreeEngine._propagate_section_id(child, lookup.section.section_id)

        # Configure sensible default child_numbering_style for the newly added child's own future children
        child_depth = lookup.depth + 1
        if child.child_numbering_style == NumberingStyle.LOWER_ALPHA and child_depth >= 1:
            child.child_numbering_style = QuestionTreeEngine._default_child_style_for_depth(child_depth)

        if index is None or index >= len(parent.children):
            parent.children.append(child)
        else:
            parent.children.insert(max(0, index), child)

        NumberingFSM.resolve_project(project)
        return child

    @staticmethod
    def move_up(project: ProjectState, question_id: str) -> bool:
        """Move a question or subquestion one position up among its siblings."""
        lookup = QuestionTreeEngine.find_node(project, question_id)
        if lookup is None or lookup.index_in_siblings == 0:
            return False
        idx = lookup.index_in_siblings
        siblings = lookup.sibling_list
        siblings[idx - 1], siblings[idx] = siblings[idx], siblings[idx - 1]
        NumberingFSM.resolve_project(project)
        return True

    @staticmethod
    def move_down(project: ProjectState, question_id: str) -> bool:
        """Move a question or subquestion one position down among its siblings."""
        lookup = QuestionTreeEngine.find_node(project, question_id)
        if lookup is None or lookup.index_in_siblings >= len(lookup.sibling_list) - 1:
            return False
        idx = lookup.index_in_siblings
        siblings = lookup.sibling_list
        siblings[idx + 1], siblings[idx] = siblings[idx], siblings[idx + 1]
        NumberingFSM.resolve_project(project)
        return True

    @staticmethod
    def reparent_node(
        project: ProjectState,
        question_id: str,
        new_parent_id: Optional[str],
        target_section_id: Optional[str] = None,
        target_index: Optional[int] = None,
    ) -> QuestionNode:
        """Move/reparent a question node (and its subtree) to a new parent or top-level section."""
        lookup = QuestionTreeEngine.find_node(project, question_id)
        if lookup is None:
            raise ValueError(f"Question '{question_id}' not found.")

        moving_node = lookup.node

        if new_parent_id is not None:
            if QuestionTreeEngine.is_descendant_of(moving_node, new_parent_id):
                raise ValueError("Cannot reparent a question node into itself or one of its descendants.")
            target_parent_lookup = QuestionTreeEngine.find_node(project, new_parent_id)
            if target_parent_lookup is None:
                raise ValueError(f"Target parent '{new_parent_id}' not found.")

            # Remove from old location
            lookup.sibling_list.pop(lookup.index_in_siblings)

            moving_node.parent_id = target_parent_lookup.node.question_id
            QuestionTreeEngine._propagate_section_id(moving_node, target_parent_lookup.section.section_id)
            dest_list = target_parent_lookup.node.children
            if target_index is None or target_index >= len(dest_list):
                dest_list.append(moving_node)
            else:
                dest_list.insert(max(0, target_index), moving_node)
        else:
            dest_section = (
                QuestionTreeEngine.find_section(project, target_section_id)
                if target_section_id
                else lookup.section
            )
            if dest_section is None:
                raise ValueError(f"Target section '{target_section_id}' not found.")

            lookup.sibling_list.pop(lookup.index_in_siblings)
            moving_node.parent_id = None
            QuestionTreeEngine._propagate_section_id(moving_node, dest_section.section_id)
            dest_list = dest_section.questions
            if target_index is None or target_index >= len(dest_list):
                dest_list.append(moving_node)
            else:
                dest_list.insert(max(0, target_index), moving_node)

        NumberingFSM.resolve_project(project)
        return moving_node

    @staticmethod
    def move_to_section(
        project: ProjectState,
        question_id: str,
        target_section_id: str,
        target_index: Optional[int] = None,
    ) -> QuestionNode:
        """Move any question node to become a top-level question in `target_section_id`."""
        return QuestionTreeEngine.reparent_node(
            project,
            question_id=question_id,
            new_parent_id=None,
            target_section_id=target_section_id,
            target_index=target_index,
        )

    @staticmethod
    def duplicate_node(project: ProjectState, question_id: str) -> QuestionNode:
        """Deep-clone a question node (including all children, options, and marks) immediately after it."""
        lookup = QuestionTreeEngine.find_node(project, question_id)
        if lookup is None:
            raise ValueError(f"Question '{question_id}' not found.")

        cloned = lookup.node.clone_with_new_ids()
        QuestionTreeEngine._propagate_section_id(cloned, lookup.section.section_id)
        insert_pos = lookup.index_in_siblings + 1
        lookup.sibling_list.insert(insert_pos, cloned)
        NumberingFSM.resolve_project(project)
        return cloned

    @staticmethod
    def delete_node(
        project: ProjectState,
        question_id: str,
        allow_with_children: bool = True,
    ) -> Tuple[QuestionNode, int]:
        """Delete a question node from `project`, returning `(deleted_node, descendant_count)`.

        If `allow_with_children=False` and the node has child subquestions, raises ValueError
        so the caller/UI can prompt the teacher for confirmation.
        """
        lookup = QuestionTreeEngine.find_node(project, question_id)
        if lookup is None:
            raise ValueError(f"Question '{question_id}' not found.")

        descendant_count = QuestionTreeEngine.count_descendants(lookup.node)
        if descendant_count > 0 and not allow_with_children:
            raise ValueError(
                f"Question '{question_id}' has {descendant_count} child subquestion(s); confirmation required."
            )

        removed = lookup.sibling_list.pop(lookup.index_in_siblings)
        # Clean up any dangling references in section choice_groups or shared_passages
        removed_ids = QuestionTreeEngine._collect_subtree_ids(removed)
        for sec in project.sections:
            for cg in sec.choice_groups:
                cg.question_ids = [qid for qid in cg.question_ids if qid not in removed_ids]
            for sp in sec.shared_passages:
                sp.linked_question_ids = [qid for qid in sp.linked_question_ids if qid not in removed_ids]

        NumberingFSM.resolve_project(project)
        return removed, descendant_count

    @staticmethod
    def _collect_subtree_ids(node: QuestionNode) -> set[str]:
        ids = {node.question_id}
        for ch in node.children:
            ids.update(QuestionTreeEngine._collect_subtree_ids(ch))
        return ids

    @staticmethod
    def _propagate_section_id(node: QuestionNode, section_id: str) -> None:
        node.section_id = section_id
        for ch in node.children:
            QuestionTreeEngine._propagate_section_id(ch, section_id)


@dataclass
class UndoSnapshotEntry:
    """Immutable serialized state snapshot in the UndoRedoManager stack."""

    description: str
    serialized_json: str


@dataclass
class UndoRedoManager:
    """Full Undo/Redo command stack preserving options, marks, numbering, and hierarchy."""

    max_history: int = 100
    _undo_stack: List[UndoSnapshotEntry] = field(default_factory=list)
    _redo_stack: List[UndoSnapshotEntry] = field(default_factory=list)

    def record_state(self, project: ProjectState, description: str = "Edit") -> None:
        """Push the current `project` state onto the undo stack before or at a mutation point."""
        NumberingFSM.resolve_project(project)
        entry = UndoSnapshotEntry(
            description=description,
            serialized_json=project.to_json_string(indent=None),
        )
        # Avoid pushing duplicate consecutive snapshots
        if self._undo_stack and self._undo_stack[-1].serialized_json == entry.serialized_json:
            return
        self._undo_stack.append(entry)
        if len(self._undo_stack) > self.max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def clear(self) -> None:
        """Reset the undo and redo history stacks."""
        self._undo_stack.clear()
        self._redo_stack.clear()

    @property
    def can_undo(self) -> bool:
        """Return True if there is a previous state to revert to."""
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        """Return True if there is a forward state to re-apply."""
        return len(self._redo_stack) > 0

    @property
    def undo_description(self) -> Optional[str]:
        """Return description of the top undo action."""
        return self._undo_stack[-1].description if self._undo_stack else None

    @property
    def redo_description(self) -> Optional[str]:
        """Return description of the top redo action."""
        return self._redo_stack[-1].description if self._redo_stack else None

    def undo(self, current_project: ProjectState) -> ProjectState:
        """Revert `current_project` to the most recent snapshot on the undo stack."""
        if not self.can_undo:
            raise RuntimeError("Undo stack is empty.")

        current_json = current_project.to_json_string(indent=None)
        top_entry = self._undo_stack.pop()

        # If top of undo stack matches current state and an earlier state exists, step back one more
        if top_entry.serialized_json == current_json and self._undo_stack:
            self._redo_stack.append(top_entry)
            target_entry = self._undo_stack.pop()
        else:
            self._redo_stack.append(
                UndoSnapshotEntry(description=top_entry.description, serialized_json=current_json)
            )
            target_entry = top_entry

        restored = ProjectState.from_json_string(target_entry.serialized_json)
        NumberingFSM.resolve_project(restored)
        return restored

    def redo(self, current_project: ProjectState) -> ProjectState:
        """Re-apply the most recently undone state from the redo stack."""
        if not self.can_redo:
            raise RuntimeError("Redo stack is empty.")

        current_json = current_project.to_json_string(indent=None)
        next_entry = self._redo_stack.pop()
        self._undo_stack.append(
            UndoSnapshotEntry(description=next_entry.description, serialized_json=current_json)
        )

        restored = ProjectState.from_json_string(next_entry.serialized_json)
        NumberingFSM.resolve_project(restored)
        return restored
