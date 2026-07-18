"""
沙箱异常定义
"""


class SandboxError(Exception):
    """沙箱基础异常"""
    pass


class SandboxCreationError(SandboxError):
    """沙箱创建失败"""
    pass


class SandboxExecutionError(SandboxError):
    """沙箱执行失败"""
    pass


class SandboxTimeoutError(SandboxError):
    """沙箱执行超时"""
    pass


class SandboxResourceError(SandboxError):
    """沙箱资源不足"""
    pass


class SandboxSecurityError(SandboxError):
    """沙箱安全违规"""
    pass


class SandboxNotFoundError(SandboxError):
    """沙箱未找到"""
    pass
