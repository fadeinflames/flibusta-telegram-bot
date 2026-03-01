NAV_STACK_KEY = "nav_stack"
MAX_NAV_STACK = 10


def push_nav(context, entry: dict):
    stack = context.user_data.setdefault(NAV_STACK_KEY, [])
    if stack and stack[-1] == entry:
        return
    stack.append(entry)
    if len(stack) > MAX_NAV_STACK:
        stack.pop(0)


def pop_nav(context):
    stack = context.user_data.get(NAV_STACK_KEY, [])
    return stack.pop() if stack else None


def reset_nav(context):
    context.user_data[NAV_STACK_KEY] = []
