def make_progress_bar(percentage: float, total_blocks: int = 10) -> str:
    percentage = max(0, min(percentage, 100))
    filled_blocks = int((percentage / 100) * total_blocks)
    empty_blocks = total_blocks - filled_blocks
    return f"`[{'■' * filled_blocks}{'□' * empty_blocks}] {percentage}%`"
