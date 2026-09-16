"""Narrow literal-inline Python triage; AST parsing only, never execution."""
import ast
import re

INLINE_PREFIX = re.compile(r'^\s*(?:python(?:\.exe)?|py)(?:\s+-u)?\s+-c\s+', re.IGNORECASE)
PLACEHOLDER = re.compile(r'<[^>]+>|\.\.\.|\{[^}]+\}')


def command_audit(command, legacy_audit):
    match = INLINE_PREFIX.match(command)
    if not match:
        return legacy_audit(command)
    tail = command[match.end():].strip()
    reasons = []
    # Narrow supported shell shape: one outer quote pair, no embedded delimiter,
    # arguments, substitutions, or escapes with ambiguous shell interpretation.
    if (len(tail) < 2 or tail[0] not in '\"\'' or tail[-1] != tail[0]
            or tail.count(tail[0]) != 2):
        reasons.append('unsupported_inline_quoting')
    elif tail[0] == '"' and ('$' in tail[1:-1] or '`' in tail[1:-1]):
        reasons.append('interpolated_inline_payload')
    else:
        source = tail[1:-1]
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError):
            reasons.append('invalid_inline_python')
        else:
            if not tree.body:
                reasons.append('empty_inline_python')
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and PLACEHOLDER.search(node.value):
                    reasons.append('contains_placeholder_string')
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and node.value.value is Ellipsis:
                    reasons.append('contains_ellipsis_stub')
    return dict(command=command, exact=not reasons, reasons=sorted(set(reasons)),
                classifier='literal_inline_python_ast_v1', validation_scope='syntax_only_not_execution_or_safety')
