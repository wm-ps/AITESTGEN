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
Journey's `TestSuite`).
"""

from domain.action import Action
from domain.api_endpoint import ApiEndpoint
from domain.application import Application, AuthMethod
from domain.assertion import Assertion
from domain.capability import Capability, CapabilityStatus
from domain.component import Component
from domain.component_locator import ComponentLocator
from domain.discovery_run import DiscoveryRun
from domain.form import Form
from domain.form_field import FormField
from domain.journey import Journey, JourneyStatus
from domain.journey_step import JourneyStep
from domain.organization import Organization
from domain.page import Page
from domain.page_transition import PageTransition
from domain.platform_user import PlatformUser
from domain.scenario import Scenario, ScenarioType
from domain.test_asset import TestAsset
from domain.test_suite import TestSuite
from domain.validation_rule import ValidationRule

__all__ = [
    "Action",
    "ApiEndpoint",
    "Application",
    "Assertion",
    "AuthMethod",
    "Capability",
    "CapabilityStatus",
    "Component",
    "ComponentLocator",
    "DiscoveryRun",
    "Form",
    "FormField",
    "Journey",
    "JourneyStatus",
    "JourneyStep",
    "Organization",
    "Page",
    "PageTransition",
    "PlatformUser",
    "Scenario",
    "ScenarioType",
    "TestAsset",
    "TestSuite",
    "ValidationRule",
]
