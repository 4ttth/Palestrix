"""PalestrIX sandbox coordinator.

Implements the detonator contract the core API's CoordinatorDetonator calls:
``POST /detonate`` with a multipart sample, answering with the verdict, score,
MITRE ids, IOCs, behaviour events and artifacts the sandbox UI renders.

The core process never touches this service's VMs, bridge or pcaps -- it sees
only the JSON described in ``backend/palestrix/sandbox/coordinator.py``.
"""
