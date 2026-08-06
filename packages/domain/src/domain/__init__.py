"""packages/domain — SQLModel entities and their invariants (architecture Structural Seed).

Story 1.1's `ScaffoldProbe` proved the wiring end-to-end and has been
removed now that the real domain model supersedes it (its own docstring
called this out as safe to do). Stories 1.2/1.3 add the real model:
`Organization`, `PlatformUser`, `Application`, `DiscoveryRun`. Story 2.2 adds
the typed capture entities (`Page`/`Form`/`FormField`/`ValidationRule`/
`Action`/`ApiEndpoint`/`PageTransition` — there is no generic `Evidence`
table, removed 2026-07-18). Story 2.5 adds the derived entities
(`Component`/`ComponentLocator`/`Assertion`). Story 2.6 adds
`Journey`/`Capability`. Story 4.1 adds `Scenario`/`JourneyStep`. Story 4.2
adds `TestSuite`/`TestAsset` (one `TestSuite` per Journey per attempt,
auto-named from the Journey; one `TestAsset` per Scenario, belonging to its
Journey's `TestSuite`). Story 2.22 adds `DiagnosticRecord`, the single sink
table every Discovery Engine v2 heuristic (2.10-2.14, 2.19, 2.21) writes
observability through.
"""

from domain.action import Action
from domain.api_endpoint import ApiEndpoint
from domain.application import Application, AuthMethod
from domain.assertion import Assertion
from domain.blocked_task import BlockedTask, BlockedTaskStatus, RequiredType
from domain.capability import Capability, CapabilityStatus
from domain.component import Component
from domain.component_locator import ComponentLocator
from domain.diagnostic_record import DiagnosticRecord
from domain.discovery_error import DiscoveryError, ErrorCode
from domain.discovery_run import DiscoveryRun
from domain.exploration_step import ExplorationStep
from domain.form import Form
from domain.form_field import FormField
from domain.invite import Invite
from domain.journey import Journey, JourneyStatus
from domain.journey_step import JourneyStep
from domain.key_normalization import aggregation_key
from domain.organization import Organization
from domain.page import Page
from domain.page_transition import PageTransition
from domain.platform_user import PlatformUser
from domain.scenario import Scenario, ScenarioType
from domain.synthetic_data_entry import SyntheticDataEntry
from domain.test_asset import TestAsset
from domain.test_data_entry import TestDataEntry
from domain.test_suite import TestSuite
from domain.validation_rule import ValidationRule

__all__ = [
    "Action",
    "ApiEndpoint",
    "Application",
    "Assertion",
    "AuthMethod",
    "BlockedTask",
    "BlockedTaskStatus",
    "RequiredType",
    "Capability",
    "CapabilityStatus",
    "Component",
    "ComponentLocator",
    "DiagnosticRecord",
    "DiscoveryError",
    "ErrorCode",
    "DiscoveryRun",
    "ExplorationStep",
    "Form",
    "FormField",
    "Invite",
    "Journey",
    "JourneyStatus",
    "JourneyStep",
    "Organization",
    "Page",
    "PageTransition",
    "PlatformUser",
    "Scenario",
    "ScenarioType",
    "SyntheticDataEntry",
    "TestAsset",
    "TestDataEntry",
    "TestSuite",
    "ValidationRule",
    "aggregation_key",
]
