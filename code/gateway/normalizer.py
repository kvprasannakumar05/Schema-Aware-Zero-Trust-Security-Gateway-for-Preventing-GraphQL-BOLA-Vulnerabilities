import base64

import graphql


class Node:

    def __init__(self, name, args=None):
        self.name = name
        self.args = args or {}
        self.children = []


def normalize(query_string, variables):
    document = graphql.parse(query_string)
    variables = variables or {}

    fragments = {
        d.name.value: d
        for d in document.definitions
        if isinstance(d, graphql.FragmentDefinitionNode)
    }
    operations = [
        d for d in document.definitions
        if isinstance(d, graphql.OperationDefinitionNode)
    ]

    def build(selection_set, seen_fragments):
        nodes = []
        if selection_set is None:
            return nodes
        for sel in selection_set.selections:
            if isinstance(sel, graphql.FieldNode):
                node = Node(sel.name.value, _read_args(sel, variables))
                node.children = build(sel.selection_set, seen_fragments)
                nodes.append(node)
            elif isinstance(sel, graphql.FragmentSpreadNode):
                name = sel.name.value
                if name in seen_fragments:
                    raise ValueError("fragment cycle")
                frag = fragments.get(name)
                if frag:
                    nodes.extend(build(frag.selection_set, seen_fragments | {name}))
            elif isinstance(sel, graphql.InlineFragmentNode):
                nodes.extend(build(sel.selection_set, seen_fragments))
        return nodes

    result = []
    for op in operations:
        result.append({
            "operation": op.operation.value,
            "roots": build(op.selection_set, frozenset()),
        })
    return result


def _read_args(field_node, variables):
    args = {}
    for arg in (field_node.arguments or []):
        value = _value_of(arg.value, variables)
        if arg.name.value == "id" and value is not None:
            value = _decode_global_id(str(value))
        args[arg.name.value] = value
    return args


def _value_of(value_node, variables):
    if isinstance(value_node, graphql.VariableNode):
        return variables.get(value_node.name.value)
    if isinstance(value_node, (
        graphql.IntValueNode, graphql.StringValueNode,
        graphql.FloatValueNode, graphql.BooleanValueNode,
        graphql.EnumValueNode,
    )):
        return value_node.value
    return None


def _decode_global_id(value):
    try:
        decoded = base64.b64decode(value, validate=True).decode()
        if ":" in decoded:
            return decoded.split(":", 1)[1]
    except Exception:
        pass
    return value


def _all_nodes(operations):
    out = []

    def walk(nodes):
        for n in nodes:
            out.append(n)
            walk(n.children)

    for op in operations:
        walk(op["roots"])
    return out


def contains_introspection(operations):
    return any(n.name.startswith("__") for n in _all_nodes(operations))


def count_fields(operations):
    return len(_all_nodes(operations))


def max_depth(operations):
    def depth(nodes):
        if not nodes:
            return 0
        return 1 + max(depth(n.children) for n in nodes)

    return max((depth(op["roots"]) for op in operations), default=0)
