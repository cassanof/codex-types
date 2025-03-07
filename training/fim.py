from tree_sitter import Node
from tree_sitter_languages import get_language, get_parser

import numpy as np
from numpy.random import RandomState

from typing import List, Tuple, Optional, Literal

TS_LANGUAGE = get_language("typescript")
PARSER = get_parser("typescript")

def get_prefix_middle_suffix(np_rng: RandomState, sample: bytes, strip_suffix_rate: float) -> Optional[Tuple[Tuple[str, str, str], RandomState]]:
    def is_child_type_annotation(node):
        """Checks if any of the parent nodes is an annotation node."""
        node = node.parent
        while node is not None:
            if node.type == "type_annotation" or node.type == "opting_type_annotation" or node.type == "omitting_type_annotation":
                return True
            node = node.parent
        return False

    def contains_url(node):
        # check if it contains a url, should not contain a //
        string = sample[node.start_byte:node.end_byte].decode("utf-8")
        return "//" in string

    QUERY = TS_LANGUAGE.query("""
[
  (type_annotation) @annotation
  (opting_type_annotation) @annotation
  (omitting_type_annotation) @annotation
]
""")
    tree = PARSER.parse(sample)

    # Each capture has a start_byte and end_byte; these are the indices of the
    # type annotation. We want to invert these indices, i.e. get the substrings
    # between the captures (and also the substring before the first capture and
    # the substring after the last capture).
    captures: List[Tuple[Node, str]] = QUERY.captures(tree.root_node)

    def is_splitable(node):
        return not is_child_type_annotation(node) and not contains_url(node)

    def is_capturable(node):
        return not is_child_type_annotation(node) and not contains_url(node)

    captures_no_child: List[Node] = []

    for i, (node, _) in enumerate(captures):
        if is_capturable(node):
            captures_no_child += [node]

    splittable_indices: List[int] = []

    for i, node in enumerate(captures_no_child):
        if is_splitable(node):
            splittable_indices += [i]

    if len(splittable_indices) == 0:
        return None
    random_pick_i = np_rng.choice(splittable_indices)

    prefix_b: bytes = sample[:captures_no_child[random_pick_i].start_byte]
    middle_b: bytes = sample[captures_no_child[random_pick_i]
                             .start_byte:captures_no_child[random_pick_i].end_byte]

    if middle_b.startswith(b":"):
        prefix_b += b": "
        middle_b = middle_b[1:].lstrip()
    suffix_b: bytes = b""

    # if we strip the types to the suffix:
    if np_rng.binomial(1, strip_suffix_rate):
        l = len(captures_no_child)
        for i in range(random_pick_i, l - 1):
            suffix_b += sample[captures_no_child[i]
                               .end_byte:captures_no_child[i + 1].start_byte]
        suffix_b += sample[captures_no_child[l - 1].end_byte:]
    else:  # keep the types in the suffix
        suffix_b = sample[captures_no_child[random_pick_i].end_byte:]

    prefix_str = prefix_b.decode("utf-8")
    middle_str = middle_b.decode("utf-8")
    suffix_str = suffix_b.decode("utf-8")

    return (prefix_str, middle_str, suffix_str), np_rng

SplitState = Literal["code", "hole"]
def get_multi_holes(
    np_rng: RandomState,
    sample: bytes,
    holes: int,
    strip_suffix_rate: float = 0.9,
) -> Optional[Tuple[List[Tuple[str, SplitState]], RandomState]]:
    def is_child_type_annotation(node):
        """Checks if any of the parent nodes is an annotation node."""
        node = node.parent
        while node is not None:
            if node.type == "type_annotation" or node.type == "opting_type_annotation" or node.type == "omitting_type_annotation":
                return True
            node = node.parent
        return False

    def contains_url(node):
        # check if it contains a url, should not contain a //
        string = sample[node.start_byte:node.end_byte].decode("utf-8")
        return "//" in string

    QUERY = TS_LANGUAGE.query("""
[
  (type_annotation) @annotation
  (opting_type_annotation) @annotation
  (omitting_type_annotation) @annotation
]
""")
    tree = PARSER.parse(sample)

    # Each capture has a start_byte and end_byte; these are the indices of the
    # type annotation. We want to invert these indices, i.e. get the substrings
    # between the captures (and also the substring before the first capture and
    # the substring after the last capture).
    captures: List[Tuple[Node, str]] = QUERY.captures(tree.root_node)

    def is_splitable(node):
        return not is_child_type_annotation(node) and not contains_url(node)

    def is_capturable(node):
        return not is_child_type_annotation(node) and not contains_url(node)

    captures_no_child: List[Node] = []

    for i, (node, _) in enumerate(captures):
        if is_capturable(node):
            captures_no_child += [node]

    splittable_indices: List[int] = []

    for i, node in enumerate(captures_no_child):
        if is_splitable(node):
            splittable_indices += [i]

    if len(splittable_indices) == 0:
        return None
    
    if len(splittable_indices) <= holes:
        picked_holes = splittable_indices
    else:
        random_pick_i: int = np_rng.choice(splittable_indices)
        random_pick_i_i = splittable_indices.index(random_pick_i)
        holes = min(holes, len(splittable_indices))
        before = random_pick_i_i - holes // 2
        after = random_pick_i_i + holes // 2
        before = max(0, before)
        after = min(len(splittable_indices), after)
        picked_holes = splittable_indices[before:after]

    splits = []
    splits.append((sample[:captures_no_child[picked_holes[0]].start_byte], "code"))
    for i in picked_holes:
        hole = sample[captures_no_child[i].start_byte:captures_no_child[i].end_byte]
        if hole.startswith(b":"):
            hole = hole[1:].lstrip()
            splits[-1] = (splits[-1][0] + b": ", "code")
        splits.append((hole, "hole"))
        if i < picked_holes[-1]:
            after = sample[captures_no_child[i].end_byte:captures_no_child[i+1].start_byte]
            splits.append((after, "code"))


    suffix_b: bytes = b""
    if np_rng.binomial(1, strip_suffix_rate):
        l = len(captures_no_child)
        for i in range(picked_holes[-1], l - 1):
            suffix_b += sample[captures_no_child[i]
                               .end_byte:captures_no_child[i + 1].start_byte]
        suffix_b += sample[captures_no_child[l - 1].end_byte:]
    else:
        suffix_b = sample[captures_no_child[picked_holes[-1]].end_byte:]

    splits.append((suffix_b, "code"))


    return [(s[0].decode("utf-8"), s[1]) for s in splits], np_rng

def permute_multi_holes(
    sample,
    np_rng,
    strip_suffix_rate=0.9,
) -> Tuple[Optional[str], RandomState]:
    try:
        res = get_multi_holes(np_rng, sample, 6, strip_suffix_rate)
    except Exception:
        return None, np_rng

    if res is None:
        return None, np_rng

    holes, np_rng = res
    buf = ""
    hole_buf = ""
    for hole, state in holes:
        if state == "code":
            buf += hole
        else:
            buf += f"<hole>"
            hole_buf += f"<fill>{hole}"

    buf += hole_buf
    return buf, np_rng


if __name__ == "__main__":  # some unit tests
    import os
    rng = np.random.RandomState(seed=int(os.urandom(4).hex(), 16))
    sample = """
    interface Foo {
         foo(x: bool, y: string): string;
         name: {
             first: string;
             last: {
                 name: string;
                 age: number;
             };
         };
     }
 
     function foo(x: number, y:number): number {
         return x + y;
     }

    // some unicode to mess things up
    // 😀 😃 😄 😁 😆 😅

    function foo2(x:number, y: bool): number {
        return x + y;
    }

    interface Bar {
        bar(x: number, y: bool): number;
        name: {
            first: string;
            last: string;
        };
    }
                

    function url() {
        let url = `https://127.0.0.1:${SUBSTRATE_PORT}`
    }
    """
    bytes_sample = bytes(sample, "utf-8")
    print("sample:", sample)
    print("bytes_sample:", bytes_sample)

    print("multi holes:")
    res = get_multi_holes(rng, bytes_sample, 6, 0.5)
    if res is not None:
        print()
        for i, s in enumerate(res[0]):
            print(f"<{s[1]}>{s[0]}</{s[1]}>", end="")

    print()
    print("permute multi holes:")
    res = permute_multi_holes(bytes_sample, rng, 0.5)
    if res is not None:
        print(res[0])

