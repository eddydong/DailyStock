"""One in-flight fetch per host that answers 429 when several land together.

Analysts overlap while they wait on the model. That wait is the slow part,
and overlapping it is what shortens a Cloud Run task. The fetches do not
overlap: Yahoo, Reddit, and the Hong Kong sources fail the burst, and the
backoff then spends the free-tier seconds the shorter run was meant to save.
"""

import threading

yahoo = threading.Lock()
hk = threading.Lock()
# The Reddit 429 path calls itself, so the same thread must be able to re-enter.
reddit = threading.RLock()
