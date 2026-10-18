"""Atomic JSON writes, validated backups and explicit recovery consent."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
import uuid
from datetime import datetime, timezone
from game_state import GameState

class PersistenceError(Exception):
    """A human-readable storage error."""

@dataclass
class LoadResult:
    state: GameState
    warning: str = ""
    needs_consent: bool = False

class SaveStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "save.json"
        self.backup = directory / "save.backup.json"
        self.allow_write = True

    @staticmethod
    def _read(path: Path) -> GameState:
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("Файл сохранения слишком большой")
        return GameState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def load(self) -> LoadResult:
        errors = []
        for path in (self.path, self.backup):
            try:
                state = self._read(path)
            except FileNotFoundError:
                continue
            except (OSError, ValueError, ArithmeticError) as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            if path == self.path:
                return LoadResult(state)
            if errors:
                self.allow_write = False
                return LoadResult(state,
                    "Основное сохранение недоступно или повреждено. Загружена резервная копия. "
                    "Последние изменения могли не попасть в неё.\n\n" + "\n".join(errors), True)
            return LoadResult(state, "Основное сохранение отсутствует. Загружена резервная копия.")
        if errors:
            self.allow_write = False
            return LoadResult(GameState(),
                "Не удалось восстановить прогресс. Запущена новая сессия без записи на диск.\n\n"
                + "\n".join(errors), True)
        return LoadResult(GameState())

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".save-", suffix=".tmp",
                                             delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _valid_or_archive(self, path: Path) -> bool:
        try:
            self._read(path)
            return True
        except FileNotFoundError:
            return False
        except (ValueError, ArithmeticError):
            # Preserve the original bytes BEFORE any overwrite. Exclusive create.
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            archive = path.with_name(f"{path.stem}.invalid-{stamp}-{uuid.uuid4().hex[:8]}.json")
            with archive.open("xb") as handle:
                handle.write(path.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            return False
        # OSError intentionally propagates: inaccessible files must not be replaced.

    def save(self, state: GameState) -> None:
        if not self.allow_write:
            raise PersistenceError("Запись отключена: восстановление не подтверждено")
        try:
            payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2,
                                 allow_nan=False).encode("utf-8")
            GameState.from_dict(json.loads(payload))  # Validate before touching disk.
            self.directory.mkdir(parents=True, exist_ok=True)
            valid_primary = self._valid_or_archive(self.path)
            if valid_primary:
                self._valid_or_archive(self.backup)
                self._atomic_write(self.backup, self.path.read_bytes())
            self._atomic_write(self.path, payload)
        except (OSError, ValueError, ArithmeticError) as exc:
            raise PersistenceError(f"Не удалось сохранить игру: {exc}") from exc

