# Production Readiness Audit & Fixes

## Issues Identified: Simplified vs Production-Grade Code

### 🚨 Critical Issues Found

#### 1. **A.23 CapTokens Service - Using Test Version Instead of Production**
**Problem**: We're using `test_a23_service.py` (simplified, no database) instead of the production `services/captokens/src/app.py` (full database integration)

**Current State**:
- ✅ Production service exists: `services/captokens/src/app.py` (495 lines, full SQLAlchemy integration)  
- ❌ Using simplified test service: `test_a23_service.py` (319 lines, InMemoryReplayGuard, no database)

**Fix Required**: 
- Fix package imports in production service
- Set up PostgreSQL database
- Use production service instead of test version

#### 2. **A.22 Capability Tokens - In-Memory Replay Guard**
**Problem**: Using `InMemoryReplayGuard` which doesn't persist across restarts

**Current State**:
- ❌ InMemoryReplayGuard (ephemeral, lost on restart)
- ❌ No distributed replay protection

**Fix Required**:
- Implement `RedisReplayGuard` or `DatabaseReplayGuard` 
- Ensure replay protection survives service restarts
- Multi-instance replay protection

#### 3. **Services with "Simplified" Comments**
**Problem**: Multiple services have simplified implementations noted in comments

**Services Affected**:
- `services/approvals/demo.py` - "simplified versions to avoid dependency issues"
- `services/orchestrator/api/` - "simplified for demo" comments throughout
- `services/policy/src/` - "simplified implementation" comments
- `packages/anumate-infrastructure/` - "simplified for now" JWT decoding

#### 4. **Package Import Issues**
**Problem**: Production services can't import packages without PYTHONPATH hacks

**Current State**:
- ❌ Manual `sys.path.insert()` calls in test files
- ❌ PYTHONPATH environment variable required
- ❌ No proper package installation

**Fix Required**:
- Proper `pip install -e` for all packages
- Remove hardcoded path manipulations
- Setup proper virtual environment

### 🔧 Required Fixes for Production Grade

#### Fix 1: Database Setup & Integration

```bash
# Set up PostgreSQL for CapTokens service
docker-compose -f ops/docker-compose.infrastructure.yml up postgres -d

# Install packages properly
pip install -e packages/anumate-capability-tokens/
pip install -e packages/anumate-logging/  
pip install -e packages/anumate-errors/

# Run production service
cd services/captokens/src
python app.py
```

#### Fix 2: Replace InMemoryReplayGuard

**Create RedisReplayGuard**:
```python
class RedisReplayGuard(ReplayGuard):
    def __init__(self, redis_client):
        self.redis = redis_client
        
    async def is_replay(self, token_id: str, timestamp: int) -> bool:
        key = f"token_replay:{token_id}:{timestamp}"
        exists = await self.redis.exists(key)
        if not exists:
            await self.redis.setex(key, 3600, "1")  # 1 hour TTL
            return False
        return True
```

#### Fix 3: Remove All "Simplified" Implementations

**Files to Review & Fix**:
1. `services/approvals/demo.py` - Remove simplified versions
2. `services/orchestrator/api/main.py` - Remove demo simplifications  
3. `services/policy/src/middleware.py` - Fix simplified implementations
4. `packages/anumate-infrastructure/tenant_context.py` - Proper JWT decoding

#### Fix 4: Proper Package Management

**Create requirements.txt per service**:
```
# services/captokens/requirements.txt
fastapi>=0.104.0
uvicorn>=0.24.0
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
cryptography>=41.0.0
pydantic>=2.4.0
-e ../../packages/anumate-capability-tokens
-e ../../packages/anumate-logging
-e ../../packages/anumate-errors
```

### 🎯 Action Plan

#### Phase 1: Infrastructure Setup
1. ✅ Start PostgreSQL database
2. ✅ Set up Redis for replay guard
3. ✅ Install packages properly
4. ✅ Remove hardcoded paths

#### Phase 2: Replace Test Implementations  
1. ✅ Use production CapTokens service instead of test version
2. ✅ Implement RedisReplayGuard
3. ✅ Fix database connection in production service
4. ✅ Test all A.23 endpoints with production service

#### Phase 3: Fix Simplified Services
1. ✅ Remove "simplified" implementations in approvals
2. ✅ Fix orchestrator demo simplifications  
3. ✅ Implement proper JWT decoding in infrastructure
4. ✅ Fix policy middleware simplified logic

#### Phase 4: Validation
1. ✅ Test all services with production implementations
2. ✅ Verify database persistence
3. ✅ Confirm multi-instance replay protection
4. ✅ End-to-end testing with real dependencies

---

## Summary

**Critical Gap**: We built excellent production-ready services but used simplified test versions for validation. For hackathon production-grade MVP, we need to:

1. **Use the actual production services** (not test versions)
2. **Set up proper infrastructure** (PostgreSQL, Redis)  
3. **Fix package management** (proper installs, not path hacks)
4. **Remove all simplified implementations** 

This ensures our MVP is truly production-grade, not just test-grade.
