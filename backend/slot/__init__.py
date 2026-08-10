# backend/slot — cấp phát 100 slot đáp án từ top-K shot (BUILD_TASKS D3.1)
#
# Cho phép import gọn: from backend.slot import allocate

from backend.slot.allocator import ShotHit, allocate

__all__ = ["ShotHit", "allocate"]
