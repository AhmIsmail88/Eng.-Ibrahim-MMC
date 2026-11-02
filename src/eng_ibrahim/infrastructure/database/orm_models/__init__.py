from .attachments import Attachment  # noqa: F401
from .base import Base
from .inventory import (  # noqa: F401
    Part,
    PartCompatibility,
    StockBalance,
    StockMovement,
    StockReservation,
    Warehouse,
)
from .maintenance import (  # noqa: F401
    DowntimeEvent,
    FailureReport,
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderExternalExpense,
    WorkOrderStatusEvent,
    WorkOrderTask,
    WorkOrderTimeLog,
)
from .operations import (  # noqa: F401
    Asset,
    AssetLocationHistory,
    AssetSpecification,
    AssetStatusHistory,
    CalendarException,
    CalendarExceptionShift,
    MeterDefinition,
    MeterReading,
    OperatingCalendar,
    OperatingCalendarShift,
    Supplier,
    Technician,
    Vehicle,
)
from .preventive import (  # noqa: F401
    Inspection,
    InspectionAnswer,
    InspectionTemplate,
    InspectionTemplateItem,
    PMOccurrence,
    PMPlan,
    PMPlanTask,
)
from .purchase import PurchaseRequest, PurchaseRequestLine  # noqa: F401
from .reference import (  # noqa: F401
    AssetCategory,
    AssetType,
    Currency,
    FailureCode,
    Location,
    MaintenanceTask,
    Unit,
)
from .system import (  # noqa: F401
    AppSetting,
    AppUser,
    AuditLog,
    BackupHistory,
    CodeSequence,
    ImportBatch,
    LocalRecoveryCode,
    Notification,
    ReportExportHistory,
)

__all__ = ["Base"]
