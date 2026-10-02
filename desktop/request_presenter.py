"""Readable request text and a deliberately narrow routine-operation policy."""
import json
import re


def readable(value):
    """Decode serialized display strings without corrupting ordinary Chinese."""
    for _ in range(3):
        if isinstance(value, dict):
            value = next((value[key] for key in ('question', 'label', 'text', 'title', 'answer') if value.get(key)), '')
        elif isinstance(value, str):
            value = value.strip()
            if value.startswith(('{', '[', '"')):
                try:
                    parsed = json.loads(value)
                except (ValueError, TypeError):
                    break
                if parsed == value:
                    break
                value = parsed
            else:
                break
        else:
            break
    if not isinstance(value, str):
        return ''
    value = re.sub(r'(?:\\+u[0-9a-fA-F]{4})+', lambda match: json.loads('"' + ''.join('\\u' + code for code in re.findall(r'u([0-9a-fA-F]{4})', match[0])) + '"'), value)
    return ''.join(char for char in value if char in '\n\t' or (ord(char) >= 32 and not 0xD800 <= ord(char) <= 0xDFFF)).strip()


def question_text(value):
    text = readable(value)
    if not text or text.startswith(('{', '[')) or re.fullmatch(r'[a-fA-F0-9-]{20,}', text):
        raise ValueError('请用用户能理解的完整中文问题提问，不要发送 JSON、内部编号或工具参数。')
    return text


def redundant_question(text):
    return bool(re.search(r'(?:可以|能否|是否|要不要|需不需要).{0,6}(?:开始|继续)(?:了|吗|执行|处理|任务|工作|[？?])|(?:允许|同意|确认).{0,8}(?:读取文件|查看目录|搜索文件|执行命令)', text))


def routine_command(command, guard):
    from routine_queries import is_routine_query
    return is_routine_query(command,guard)


def command_request(command, workspace, guard, purpose=''):
    routine = routine_command(command, guard)
    lower = command.lower()
    summaries = (
        (r'remove-item|\brmdir\b|\bdel\b', '删除文件或文件夹', '删除可能影响已有文件，请确认具体路径。'),
        (r'\bgit\s+push\b', '把代码推送到远程仓库', '会把本地提交上传到远程仓库。'),
        (r'\bgit\s+(reset|clean)\b', '清理或重置项目内容', '可能移除本地修改或文件，请检查详情。'),
        (r'\b(pip|npm|pnpm|winget|uv)\b.*\b(install|add|sync)\b', '安装项目需要的软件或依赖', '会下载软件并修改相应环境或项目依赖。'),
        (r'pytest|unittest|\btest\b|check_\w+\.py', '运行项目检查', '会运行项目代码；检查脚本可能写入测试文件。'),
        (r'invoke-webrequest|\bcurl\b|\bwget\b', '从网络获取内容', '会连接网络，命令可能保存下载的文件。'),
    )
    summary, impact = '执行当前任务需要的一步操作', '这一步可能修改文件或运行程序，请确认后执行。'
    for pattern, title, note in summaries:
        if re.search(pattern, lower):
            summary, impact = title, note
            break
    if routine:
        summary, impact = ('查找并列出项目文件' if re.search(r'\b(get-childitem|dir)\b',lower) else '查看项目资料或输出检查信息'), '只查看项目文件信息或显示文字，不修改文件。'
    elif not re.search(r'remove-item|\brmdir\b|\bdel\b|\bgit\s+|\b(pip|npm|pnpm|winget|uv)\b|pytest|unittest|\btest\b|check_\w+\.py|invoke-webrequest|\bcurl\b|\bwget\b',lower) and readable(purpose):
        summary=readable(purpose)[:180]
    return {'kind': 'command', 'summary': summary,
        'reason': readable(purpose) or '为完成当前任务，需要执行这一步。',
        'location': str(workspace), 'impact': impact, 'raw': command, 'routine': routine}


def browser_request(action, target, value, exact, purpose=''):
    name = readable(target.get('label')) or {'input': '输入框', 'button': '按钮', 'select': '下拉选项', 'a': '链接'}.get(target.get('tag'), '网页控件')
    verb = {'click': '点击', 'fill': '填写', 'select': '选择', 'press': '按键操作'}[action]
    sensitive = bool(re.search(r'删除|付款|支付|购买|发送|发布|提交|保存|确认|授权|上传|退出|delete|pay|buy|send|publish|submit|save|confirm|upload|logout', name, re.I))
    routine = not target.get('hidden') and not sensitive and (
        (action == 'fill' and (target.get('type') == 'search' or re.search(r'搜索|查找|search', name, re.I)))
        or (action == 'click' and target.get('role') == 'tab')
        or (action == 'press' and value in ('Tab', 'Escape')))
    return {'kind': 'browser', 'summary': verb + '“' + name[:160] + '”',
        'reason': readable(purpose) or '为继续完成当前网页任务，需要操作这个控件。',
        'location': target['url'], 'value': readable(value) if value is not None else '',
        'impact': '可能向网页提交内容或更改网页状态，请确认操作目标。',
        'raw': exact, 'routine': bool(routine)}
