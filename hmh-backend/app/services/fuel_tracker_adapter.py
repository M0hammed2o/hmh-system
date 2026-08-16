"""Provider-neutral vehicle tracker boundary used by Fuel Management.

No vendor SDK is imported by the fuel ledger. A future integration implements
``FuelTrackerAdapter`` and returns normalized, timestamped readings.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol
import uuid


@dataclass(frozen=True)
class TrackerReading:
    vehicle_id: uuid.UUID
    provider: str
    external_vehicle_id: str
    recorded_at: datetime
    odometer_km: Optional[float] = None
    trip_distance_km: Optional[float] = None
    engine_hours: Optional[float] = None
    ignition_duration_hours: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class FuelTrackerAdapter(Protocol):
    def latest_reading(self, *, vehicle_id: uuid.UUID, provider: str,
                       external_vehicle_id: str) -> Optional[TrackerReading]: ...


class NullFuelTrackerAdapter:
    """Default adapter: manual and photo-verified capture remain available."""

    def latest_reading(self, *, vehicle_id: uuid.UUID, provider: str,
                       external_vehicle_id: str) -> Optional[TrackerReading]:
        return None


tracker_adapter: FuelTrackerAdapter = NullFuelTrackerAdapter()
