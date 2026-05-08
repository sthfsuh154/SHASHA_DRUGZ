import socket
import time
import heroku3
from pyrogram import filters
from pyrogram.filters import Filter
import config
from SHASHA_DRUGZ.core.mongo import mongodb
from .logging import LOGGER


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — Define the working filter class FIRST
# ══════════════════════════════════════════════════════════════════════════════
class _UserSetFilter(Filter):
    """
    A proper Pyrogram Filter subclass backed by a plain Python set of user IDs.

    Works correctly in ALL contexts:
      ✔  handler filter            → async __call__(client, update)
      ✔  filter composition  & | ~ → Pyrogram internals call __call__, not __init__
      ✔  for uid in FILTER         → __iter__
      ✔  uid in FILTER             → __contains__
      ✔  FILTER or []              → __bool__  (configurable)
      ✔  FILTER.add(uid)           → add
      ✔  FILTER.discard(uid)       → discard
      ✔  filters.user(ids)         → monkey-patched to return this class
    """

    def __init__(self, always_truthy: bool = True):
        self._ids: set = set()
        self._always_truthy = always_truthy

    # ── Pyrogram filter protocol ──────────────────────────────────────────────
    async def __call__(self, client, update):
        user = getattr(update, "from_user", None)
        if user is None:
            return False
        return int(user.id) in self._ids

    # ── Mutable-set interface ─────────────────────────────────────────────────
    def add(self, user_id: int):
        self._ids.add(int(user_id))

    def discard(self, user_id: int):
        self._ids.discard(int(user_id))

    def remove(self, user_id: int):
        self._ids.discard(int(user_id))

    def clear(self):
        self._ids.clear()

    def update(self, iterable):
        for uid in iterable:
            self.add(uid)

    # ── Python data-model (MUST live on the class, not the instance) ─────────
    def __iter__(self):
        return iter(self._ids)

    def __contains__(self, item):
        try:
            return int(item) in self._ids
        except (TypeError, ValueError):
            return False

    def __len__(self):
        return len(self._ids)

    def __bool__(self):
        return self._always_truthy or bool(self._ids)

    def __repr__(self):
        return f"_UserSetFilter({self._ids!r})"


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — Monkey-patch filters.user GLOBALLY
#
#  Root cause: in this Pyrogram version, filters.user is a CLASS whose
#  __init__ is called instead of __call__ when Pyrogram composes filters
#  with & / | / ~.  Every plugin that writes  `filters.user(some_id)` or
#  `filters.user([])` or `& ~BANNED_USERS`  triggers the crash.
#
#  Fix: replace filters.user with a factory function that always returns
#  a _UserSetFilter.  This runs at import time, before ANY plugin loads.
# ══════════════════════════════════════════════════════════════════════════════
def _user_filter_factory(*args):
    """
    Drop-in replacement for filters.user().

    Accepts the same call signatures found in the codebase:
      filters.user()               → empty filter
      filters.user(123)            → single int
      filters.user([1, 2, 3])      → list of ints
      filters.user(1, 2, 3)        → multiple ints (some plugins do this)
    """
    f = _UserSetFilter(always_truthy=False)
    for arg in args:
        if isinstance(arg, (list, tuple, set, frozenset)):
            for uid in arg:
                try:
                    f.add(int(uid))
                except (TypeError, ValueError):
                    pass
        elif isinstance(arg, int):
            f.add(arg)
        # str/None/other types → silently ignored
    return f


# Patch both the module attribute AND the pyrogram.filters namespace so
# `from pyrogram import filters; filters.user(...)` is also covered.
filters.user = _user_filter_factory

try:
    import pyrogram.filters as _pf
    _pf.user = _user_filter_factory
except Exception:
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — Create the two global filter singletons
# ══════════════════════════════════════════════════════════════════════════════

# Always-truthy set of privileged user IDs
SUDOERS: _UserSetFilter = _UserSetFilter(always_truthy=True)

# Falsy-when-empty set of banned user IDs
BANNED_USERS: _UserSetFilter = _UserSetFilter(always_truthy=False)


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — Patch the config module so every plugin that does
#            `from config import BANNED_USERS / SUDOERS` gets our objects.
#            config.py itself has `BANNED_USERS = filters.user()` which now
#            already returns a _UserSetFilter because of the patch above,
#            but we replace the config references with our singletons so
#            BANNED_USERS.add() mutations are shared everywhere.
# ══════════════════════════════════════════════════════════════════════════════
config.BANNED_USERS = BANNED_USERS
config.SUDOERS      = SUDOERS


# ══════════════════════════════════════════════════════════════════════════════
#  Rest of misc
# ══════════════════════════════════════════════════════════════════════════════
HAPP   = None
_boot_ = time.time()


def is_heroku() -> bool:
    return "heroku" in socket.getfqdn()


XCB = [
    "/",
    "@",
    ".",
    "com",
    ":",
    "git",
    "heroku",
    "push",
    str(config.HEROKU_API_KEY),
    "https",
    str(config.HEROKU_APP_NAME),
    "HEAD",
    "master",
]


def dbb():
    global db, deploydb, mongo
    mongo    = {}
    deploydb = {}
    db       = {}
    LOGGER(__name__).info("Local Database Initialized.")


async def sudo():
    global SUDOERS

    SUDOERS.add(config.OWNER_ID)

    sudoersdb = mongodb.sudoers
    sudoers   = await sudoersdb.find_one({"sudo": "sudo"})
    sudoers   = [] if not sudoers else sudoers["sudoers"]

    if config.OWNER_ID not in sudoers:
        sudoers.append(config.OWNER_ID)
        await sudoersdb.update_one(
            {"sudo": "sudo"},
            {"$set": {"sudoers": sudoers}},
            upsert=True,
        )

    for user_id in sudoers:
        SUDOERS.add(user_id)

    LOGGER(__name__).info("Sudoers Loaded.")


def heroku():
    global HAPP
    if is_heroku():
        if config.HEROKU_API_KEY and config.HEROKU_APP_NAME:
            try:
                Heroku = heroku3.from_key(config.HEROKU_API_KEY)
                HAPP   = Heroku.app(config.HEROKU_APP_NAME)
                LOGGER(__name__).info("Heroku App Configured")
            except BaseException:
                LOGGER(__name__).warning(
                    "Please make sure your Heroku API Key and Your App name are "
                    "configured correctly in the heroku."
                )
