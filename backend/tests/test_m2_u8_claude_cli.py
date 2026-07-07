"""M2-U8：ClaudeCliEngine argv 构造（修复 --file bug）。

不真正调用 CLI，只验证命令行构造正确：
- 本地文件路径写进 prompt（而非用 --file 远程资源语义）
- 用 --add-dir 授权文件所在目录
- headless 下 bypassPermissions
"""

from pathlib import Path

from app.engine.claude_cli import ClaudeCliEngine


def test_argv_without_files_is_plain_prompt():
    engine = ClaudeCliEngine()
    argv = engine._build_argv("你好", None)
    assert argv[:3] == [engine._cli_path, "-p", "你好"]
    assert "--file" not in argv  # 不再使用 --file
    assert "--add-dir" not in argv


def test_argv_with_file_embeds_path_and_adds_dir():
    engine = ClaudeCliEngine()
    f = Path("/app/local_storage/ws1/abc.pdf")
    argv = engine._build_argv("总结这份文档", [f])

    # prompt 中包含文件路径
    prompt = argv[2]
    assert str(f) in prompt
    assert "总结这份文档" in prompt

    # 授权目录 + 仅放行 Read 工具，且绝不使用 --file
    assert "--add-dir" in argv
    assert str(f.parent) in argv
    assert "--allowedTools" in argv
    assert "Read" in argv
    assert "--file" not in argv
