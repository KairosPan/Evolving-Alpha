# youzi/application/
"""应用编排层:把领域组件(数据源 / Harness / Agent / 仓储)串成 live 用例。

**薄**:只负责顺序、冻结与落库,不重新实现任何领域逻辑;
所有取数一律经 `GuardedSource`,Agent 只拿冻结对象。
"""
from youzi.application.live_decision import LiveDecisionService

__all__ = ["LiveDecisionService"]
