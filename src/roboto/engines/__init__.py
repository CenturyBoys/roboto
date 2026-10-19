"""Motores de coding como adapters (D22): contrato comum + matriz de capacidades + stub."""

from roboto.engines.capabilities import CAPABILITIES, Capability, CapabilitySupport
from roboto.engines.port import CodingEngine, EngineEvent, EngineEventKind, RunSpec
from roboto.engines.stub import StubEngine

__all__ = [
    "CAPABILITIES",
    "Capability",
    "CapabilitySupport",
    "CodingEngine",
    "EngineEvent",
    "EngineEventKind",
    "RunSpec",
    "StubEngine",
]
