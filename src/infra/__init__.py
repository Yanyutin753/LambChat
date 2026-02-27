"""
基础设施层 (Infrastructure Layer)

提供底层服务实现，依赖 kernel 层。

包含：
- auth: 认证授权
- user: 用户管理
- role: 角色管理
- llm: LLM 客户端
- storage: 存储服务
- backend: 后端服务
- session: 会话管理
- skill: 技能管理
- tool: 工具管理
- service: 第三方服务
"""

# 各模块通过子包导入
__all__ = []
