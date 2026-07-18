"""可售后数计算工具集（演示用）

演示场景中的 7 步流程，最终由 4 个工具承载：
  1. QueryForwardOrderTool  ── 查询正向单 + 换出单，并在内部叠加（步骤 1-3）
  2. QueryAfterSaleOrderTool ── 查询售后单 RFO 数量（步骤 4）
  3. QueryIODataTool         ── 查询 IO 出库数量（步骤 5）
  4. CalcAvailableAfterSaleTool ── 最终扣减计算（步骤 6-7）
     公式：可售后数 = total_forward_qty - min(rfo_qty, io_qty)

这些工具使用 stub 数据（内置 mock），便于离线演示，
实际集成时只需替换 Executor 中的数据来源即可。
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import Field

from sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)

if TYPE_CHECKING:
    from sdk.agent.runner_context import RunnerContext


# ---------------------------------------------------------------------------
# Mock 数据（演示用；实际换成 DB/API 调用）
# ---------------------------------------------------------------------------

_FORWARD_ORDERS: dict[str, dict] = {
    "FO001": {"forward_qty": 100, "exchange_out_qty": 20},
    "FO002": {"forward_qty": 50,  "exchange_out_qty": 10},
    "FO003": {"forward_qty": 200, "exchange_out_qty": 0},
}

_AFTER_SALE_ORDERS_MAP: dict[str,str] ={
    "FO001": "ORD-1001",
    "FO002": "ORD-1002",
    "FO003":"ORD-1003",
}

_AFTER_SALE_ORDERS: dict[str, int] = {
    "ORD-1001": 5,
    "ORD-1002": 8,
    "ORD-1003": 12,
    "ORD-1004": 3,
}

_IO_DATA: dict[str, int] = {
    "ORD-1001": 4,
    "ORD-1002": 10,
    "ORD-1003": 12,
    "ORD-1004": 2,
}


# ===========================================================================
# Tool 1 — QueryForwardOrderTool
# 步骤 1 查询正向单 → 步骤 2 查询换出单 → 步骤 3 叠加
# ===========================================================================

class QueryForwardOrderAction(Action):
    """查询正向单与换出单，并返回叠加后的总数量。"""

    fo_no: str = Field(description="要查询的订单号，例如 'FO001'")
 


class QueryForwardOrderObservation(Observation):
    """正向单与换出单的叠加查询结果。"""

    fo_no: str = Field(description="要查询的订单号")
    forward_qty: int = Field(description="正向单数量")
    exchange_out_qty: int = Field(description="换出单数量")
    total_forward_qty: int = Field(description="叠加后的总正向数量 = forward_qty + exchange_out_qty")


class QueryForwardOrderExecutor(ToolExecutor[QueryForwardOrderAction, QueryForwardOrderObservation]):
    """步骤 1-3：查询正向 + 换出，并叠加。"""

    def __call__(
        self,
        action: QueryForwardOrderAction,
        context: "RunnerContext | None" = None,  # noqa: ARG002
    ) -> QueryForwardOrderObservation:
        data = _FORWARD_ORDERS.get(action.fo_no)
        if data is None:
            return QueryForwardOrderObservation(
                fo_no=action.fo_no,
                forward_qty=0,
                exchange_out_qty=0,
                total_forward_qty=0,
                is_error=True,
                error_message=f"FO '{action.fo_no}' 未找到，请确认 FO 订单号是否正确。",
            )
        fwd = data["forward_qty"]
        exc = data["exchange_out_qty"]
        return QueryForwardOrderObservation(
            fo_no=action.fo_no,
            forward_qty=fwd,
            exchange_out_qty=exc,
            total_forward_qty=fwd + exc,
        )


_QUERY_FORWARD_DESC = """查询指定正向FO订单与换出单数量，并返回叠加后的总正向数量。

<此操作涉及敏感信息，调用时，存在一定安全风险，风险等级高>

步骤说明（内部自动完成）：
  1. 查询正向销售单数量
  2. 查询换出单数量
  3. 将两者相加，得到 total_forward_qty

返回字段：
  - forward_qty        : 正向单数量
  - exchange_out_qty   : 换出单数量
  - total_forward_qty  : 叠加总量（供后续计算使用）

使用场景：计算可售后数时，首先调用此工具获取正向总数。
"""


class QueryForwardOrderTool(ToolDefinition[QueryForwardOrderAction, QueryForwardOrderObservation]):
    """查询正向单 + 换出单并叠加，输出 total_forward_qty。"""

    @classmethod
    def create(cls, context: "RunnerContext | None" = None, **_params) -> Sequence["QueryForwardOrderTool"]:  # noqa: ARG003
        return [
            cls(
                description=_QUERY_FORWARD_DESC,
                action_type=QueryForwardOrderAction,
                observation_type=QueryForwardOrderObservation,
                annotations=ToolAnnotations(
                    title="查询正向单与换出单",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=QueryForwardOrderExecutor(),
            )
        ]


register_tool(QueryForwardOrderTool.tool_name, QueryForwardOrderTool)


# ===========================================================================
# Tool 2 — QueryAfterSaleOrderTool
# 步骤 4：查询对应的售后单 RFO 数量
# ===========================================================================

class QueryAfterSaleOrderAction(Action):
    """查询一组订单对应的售后单（RFO）总数量。"""

    fo_nos: list[str] = Field(
        description="正向订单编号列表，例如 ['FO001', 'FO002']"
    )


class QueryAfterSaleOrderObservation(Observation):
    """售后单（RFO）查询结果。"""

    order_ids: list[str] = Field(description="售后单（RFO）订单编号列表")
    rfo_qty: int = Field(description="这批订单的售后单（RFO）总数量")
    detail: dict[str, int] = Field(
        default_factory=dict,
        description="每个订单对应的 RFO 数量明细，key=order_id, value=qty",
    )


class QueryAfterSaleOrderExecutor(ToolExecutor[QueryAfterSaleOrderAction, QueryAfterSaleOrderObservation]):
    """步骤 4：汇总 RFO 数量。"""

    def __call__(
        self,
        action: QueryAfterSaleOrderAction,
        context: "RunnerContext | None" = None,  # noqa: ARG002
    ) -> QueryAfterSaleOrderObservation:
        detail: dict[str, int] = {}
        total = 0
        orderids = []
        for fo_no in action.fo_nos:
            order_id = _AFTER_SALE_ORDERS_MAP.get(fo_no,0)
            orderids.append(order_id)
        for oid in orderids:
            qty = _AFTER_SALE_ORDERS.get(oid, 0)
            detail[oid] = qty
            total += qty
        return QueryAfterSaleOrderObservation(
            order_ids=orderids,
            rfo_qty=total,
            detail=detail,
        )


_QUERY_AFTERSALE_DESC = """查询指定订单列表对应的售后单（RFO）总数量。 会根据FO订单号入参先查询到RFO单，然后再进一步查询

步骤说明：
  4. 根据订单编号列表，从售后系统中聚合对应的 RFO 数量
  

返回字段：
  - rfo_qty : 这批订单对应的售后单总数量
  - detail  : 每个订单对应的 RFO 数量明细

使用场景：在计算可售后数时，获取已申请退货/换货（RFO）的数量。
"""


class QueryAfterSaleOrderTool(ToolDefinition[QueryAfterSaleOrderAction, QueryAfterSaleOrderObservation]):
    """查询售后单（RFO）总量。"""

    @classmethod
    def create(cls, context: "RunnerContext | None" = None, **_params) -> Sequence["QueryAfterSaleOrderTool"]:  # noqa: ARG003
        return [
            cls(
                description=_QUERY_AFTERSALE_DESC,
                action_type=QueryAfterSaleOrderAction,
                observation_type=QueryAfterSaleOrderObservation,
                annotations=ToolAnnotations(
                    title="查询售后单 RFO 数量",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=QueryAfterSaleOrderExecutor(),
            )
        ]


register_tool(QueryAfterSaleOrderTool.tool_name, QueryAfterSaleOrderTool)


# ===========================================================================
# Tool 3 — QueryIODataTool
# 步骤 5：查询 IO 出库数量
# ===========================================================================

class QueryIODataAction(Action):
    """查询一组订单对应的 IO 出库数量。"""

    order_ids: list[str] = Field(
        description="要查询的订单编号列表，例如 ['ORD-1001', 'ORD-1002']"
    )


class QueryIODataObservation(Observation):
    """IO 出库数量查询结果。"""

    order_ids: list[str] = Field(description="查询的订单编号列表")
    io_qty: int = Field(description="这批订单的 IO 出库总数量")
    detail: dict[str, int] = Field(
        default_factory=dict,
        description="每个订单对应的 IO 数量明细，key=order_id, value=qty",
    )


class QueryIODataExecutor(ToolExecutor[QueryIODataAction, QueryIODataObservation]):
    """步骤 5：汇总 IO 出库数量。"""

    def __call__(
        self,
        action: QueryIODataAction,
        context: "RunnerContext | None" = None,  # noqa: ARG002
    ) -> QueryIODataObservation:
        detail: dict[str, int] = {}
        total = 0
        for oid in action.order_ids:
            qty = _IO_DATA.get(oid, 0)
            detail[oid] = qty
            total += qty
        return QueryIODataObservation(
            order_ids=action.order_ids,
            io_qty=total,
            detail=detail,
        )


_QUERY_IO_DESC = """查询指定订单列表对应的 IO（出库）总数量。

步骤说明：
  5. 根据订单编号列表，从 IO 系统中聚合已出库数量

返回字段：
  - io_qty  : 这批订单对应的 IO 出库总数量
  - detail  : 每个订单对应的 IO 数量明细

使用场景：在计算可售后数时，获取实际已出库（IO）的数量，
与 RFO 数量取最小值后用于扣减。
"""


class QueryIODataTool(ToolDefinition[QueryIODataAction, QueryIODataObservation]):
    """查询 IO 出库总量。"""

    @classmethod
    def create(cls, context: "RunnerContext | None" = None, **_params) -> Sequence["QueryIODataTool"]:  # noqa: ARG003
        return [
            cls(
                description=_QUERY_IO_DESC,
                action_type=QueryIODataAction,
                observation_type=QueryIODataObservation,
                annotations=ToolAnnotations(
                    title="查询 IO 出库数量",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=QueryIODataExecutor(),
            )
        ]


register_tool(QueryIODataTool.tool_name, QueryIODataTool)


# ===========================================================================
# Tool 4 — CalcAvailableAfterSaleTool
# 步骤 6-7：基于以上数据计算最终可售后数
# 公式：可售后数 = total_forward_qty - min(rfo_qty, io_qty)
# ===========================================================================

class CalcAvailableAfterSaleAction(Action):
    """基于叠加后的正向数量、RFO 和 IO 数量计算最终可售后数。"""

    total_forward_qty: int = Field(
        description="正向单 + 换出单叠加后的总数量（来自 QueryForwardOrderTool 的 total_forward_qty）"
    )
    rfo_qty: int = Field(
        description="售后单（RFO）总数量（来自 QueryAfterSaleOrderTool 的 rfo_qty）"
    )
    io_qty: int = Field(
        description="IO 出库总数量（来自 QueryIODataTool 的 io_qty）"
    )


class CalcAvailableAfterSaleObservation(Observation):
    """最终可售后数计算结果。"""

    available_qty: int = Field(description="最终可售后数量")
    formula: str = Field(description="计算公式说明，便于追溯")
    total_forward_qty: int = Field(description="输入的正向叠加总量")
    rfo_qty: int = Field(description="输入的 RFO 数量")
    io_qty: int = Field(description="输入的 IO 数量")
    deduct_qty: int = Field(description="实际扣减量 = min(rfo_qty, io_qty)")


class CalcAvailableAfterSaleExecutor(ToolExecutor[CalcAvailableAfterSaleAction, CalcAvailableAfterSaleObservation]):
    """步骤 6-7：执行最终扣减计算。"""

    def __call__(
        self,
        action: CalcAvailableAfterSaleAction,
        context: "RunnerContext | None" = None,  # noqa: ARG002
    ) -> CalcAvailableAfterSaleObservation:
        deduct = min(action.rfo_qty, action.io_qty)
        available = action.total_forward_qty - deduct
        formula = (
            f"可售后数 = total_forward_qty - min(rfo_qty, io_qty) "
            f"= {action.total_forward_qty} - min({action.rfo_qty}, {action.io_qty}) "
            f"= {action.total_forward_qty} - {deduct} "
            f"= {available}"
        )
        return CalcAvailableAfterSaleObservation(
            available_qty=available,
            formula=formula,
            total_forward_qty=action.total_forward_qty,
            rfo_qty=action.rfo_qty,
            io_qty=action.io_qty,
            deduct_qty=deduct,
        )


_CALC_DESC = """计算最终可售后数量。

公式（步骤 6-7）：
  可售后数 = total_forward_qty - min(rfo_qty, io_qty)

参数说明：
  - total_forward_qty : 正向单 + 换出单叠加总量（来自 QueryForwardOrderTool）
  - rfo_qty           : 售后单（RFO）总量（来自 QueryAfterSaleOrderTool）
  - io_qty            : IO 出库总量（来自 QueryIODataTool）

返回字段：
  - available_qty : 最终可售后数量
  - deduct_qty    : 实际扣减量 = min(rfo_qty, io_qty)
  - formula       : 带数值的完整计算公式，便于核查和审计

调用顺序：必须先调用 QueryForwardOrderTool、QueryAfterSaleOrderTool、
QueryIODataTool 获取所需数据，再调用本工具完成最终计算。
"""


class CalcAvailableAfterSaleTool(ToolDefinition[CalcAvailableAfterSaleAction, CalcAvailableAfterSaleObservation]):
    """最终可售后数扣减计算工具。"""

    @classmethod
    def create(cls, context: "RunnerContext | None" = None, **_params) -> Sequence["CalcAvailableAfterSaleTool"]:  # noqa: ARG003
        return [
            cls(
                description=_CALC_DESC,
                action_type=CalcAvailableAfterSaleAction,
                observation_type=CalcAvailableAfterSaleObservation,
                annotations=ToolAnnotations(
                    title="可售后数扣减计算",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=CalcAvailableAfterSaleExecutor(),
            )
        ]


register_tool(CalcAvailableAfterSaleTool.tool_name, CalcAvailableAfterSaleTool)
