# Contributing to Anumate Platform

## 📁 Repository Organization

Please maintain the organized structure when contributing:

### 🔄 File Placement Guidelines

| File Type | Location | Examples |
|-----------|----------|----------|
| **Service Code** | `services/<service-name>/` | FastAPI apps, business logic |
| **Shared Packages** | `packages/anumate-<name>/` | Reusable Python packages |
| **Documentation** | `docs/` | Architecture, API docs, guides |
| **Infrastructure** | `ops/` | Docker, K8s, Terraform |
| **Schemas** | `schemas/` | OpenAPI specs, data models |
| **Scripts** | `scripts/` | Utility and demo scripts |
| **Tests (Global)** | `tests/` | Integration and e2e tests |
| **Build Artifacts** | `build/` | Generated files, distributions |
| **Logs** | `logs/` | Application log files |
| **Archive** | `archive/` | Legacy/historical content |

### 🚫 Avoid Root Directory Clutter

Keep the repository root clean by placing files in appropriate subdirectories:

- ❌ Don't add: `my_test.py`, `debug.py`, `temp_file.md` to root
- ✅ Do add: to `archive/legacy-tests/`, `scripts/`, or `docs/`

## 🧪 Testing Structure

- **Unit Tests**: Within service directories (`services/*/tests/`)
- **Integration Tests**: In global `tests/` directory  
- **Legacy Tests**: In `archive/legacy-tests/` (preserved but not active)

## 📝 Documentation

- **Architecture**: `ARCHITECTURE.md` (high-level structure)
- **Project Structure**: `PROJECT_STRUCTURE.md` (detailed file organization)
- **Service Docs**: `services/*/README.md` (service-specific docs)
- **Development**: `docs/DEVELOPMENT.md` (dev setup and guidelines)

## 🔧 Development Workflow

1. **Create Feature Branch**: `git checkout -b feature/your-feature`
2. **Place Files Appropriately**: Follow the organization guidelines above
3. **Update Documentation**: If adding new services or major changes
4. **Run Tests**: `make accept` for core functionality
5. **Clean Commit**: Ensure no temporary files in root directory

## 🏗️ Build & Release

```bash
# Generate submission package
repomix                    # Outputs to build/repomix-output.xml

# Run acceptance tests  
make accept               # Core functionality validation

# Full production demo
make demo                 # End-to-end workflow test
```

## 🎯 Judge Mode (WeMakeDevs AgentHack 2025)

For competition evaluation:
- Main docs: `services/orchestrator/JUDGE_MODE.md`  
- Demo script: `services/orchestrator/demo.sh`
- Evidence capture: `scripts/capture_evidence.py`
- Receipt verification: `scripts/verify_receipt.py`

---

**Remember**: A well-organized repository is easier to navigate, understand, and maintain! 🚀
