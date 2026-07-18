from abc import ABC, abstractmethod

from pydantic import field_validator

from sdk.event.llm_convertible.action import ActionEvent
from sdk.security.risk import SecurityRisk
from common.utils.models import DiscriminatedUnionMixin


class ConfirmationPolicyBase(DiscriminatedUnionMixin, ABC):
    @abstractmethod
    def should_confirm(self, action_event: ActionEvent, risk: SecurityRisk = SecurityRisk.UNKNOWN) -> bool:
        """Determine if an action with the given risk level requires confirmation.

        This method defines the core logic for determining whether user confirmation
        is required before executing an action based on its security risk level.

        Args:
            risk: The security risk level of the action to be evaluated.
                 Defaults to SecurityRisk.UNKNOWN if not specified.

        Returns:
            True if the action requires user confirmation before execution,
            False if the action can proceed without confirmation.
        """


class AlwaysConfirm(ConfirmationPolicyBase):
    def should_confirm(
        self
        , action_event: ActionEvent,
        risk: SecurityRisk = SecurityRisk.UNKNOWN,  # noqa: ARG002
    ) -> bool:
        return True


class NeverConfirm(ConfirmationPolicyBase):
    def should_confirm(
        self
        , action_event: ActionEvent,
        risk: SecurityRisk = SecurityRisk.UNKNOWN,  # noqa: ARG002
    ) -> bool:
        return False


class ConfirmRiskyAndAction(ConfirmationPolicyBase):
    threshold: SecurityRisk = SecurityRisk.HIGH
    confirm_unknown: bool = True
    need_confirm_name: list[str] = []

    @field_validator("threshold")
    def validate_threshold(cls, v: SecurityRisk) -> SecurityRisk:
        if v == SecurityRisk.UNKNOWN:
            raise ValueError("Threshold cannot be UNKNOWN")
        return v

    def should_confirm(self, action_event: ActionEvent, risk: SecurityRisk = SecurityRisk.UNKNOWN) -> bool:
        
        tool_name = action_event.tool_name
        
        # 从配置中获取拦截tools的配置
        if tool_name in self.need_confirm_name:
            return True
        
        if risk == SecurityRisk.UNKNOWN:
            return self.confirm_unknown

        # This comparison is reflexive by default, so if the threshold is HIGH we will
        # still require confirmation for HIGH risk actions. And since the threshold is
        # guaranteed to never be UNKNOWN (by the validator), we're guaranteed to get a
        # boolean here.
        return risk.is_riskier(self.threshold)

