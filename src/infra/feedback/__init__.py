"""
Feedback 模块

提供用户反馈的存储和管理功能。
"""

from src.infra.feedback.manager import FeedbackManager
from src.infra.feedback.storage import FeedbackStorage

__all__ = ["FeedbackStorage", "FeedbackManager"]
