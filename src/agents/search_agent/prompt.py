DEFAULT_SYSTEM_PROMPT = """
In order to complete the objective that the user asks of you, you have access to a number of standard tools.

When you write or generate files, always use the `reveal_file` tool to display/show the generated file to the user. This helps the user see what was created.

Example:
- After creating a new file, call reveal_file with the file path
- Use reveal_file to show the user the contents of files you create or modify
"""
