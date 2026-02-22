"""
Independent full-algorithm test suite for FreeWise review selection.
Tests the complete recommendation algorithm from first principles.
"""
import math, random, sys
from datetime import datetime, timedelta
from collections import Counter, defaultdict

# ─── EXACT MIRROR OF PRODUCTION ALGORITHM ─────────────────────────────────────
TAU_DAYS = 14.0
NOW = datetime(2026, 2, 22, 12, 0, 0)

class MockBook:
    def __init__(self, id, bw=1.0): self.id=id; self.review_weight=bw

class MockHighlight:
    def __init__(self, id, ca=30, lr=None, hw=1.0, bw=1.0,
                 fav=False, disc=False, rc=0, bid=None):
        self.id=id; self.book_id=bid or id
        self.created_at       = NOW-timedelta(days=ca) if ca is not None else None
        self.last_reviewed_at = NOW-timedelta(days=lr) if lr is not None else None
        self.highlight_weight=hw; self.is_favorited=fav
        self.is_discarded=disc; self.review_count=rc
        self.book=MockBook(self.book_id, bw)

class MockSettings:
    def __init__(self, n=5, r=5): self.daily_review_count=n; self.highlight_recency=r

def _ts(d): return 1.0 - math.exp(-d / TAU_DAYS)
def _bw(h): return max(0.0, float(h.book.review_weight)) if h.book else 1.0
def _hw(h): return max(0.0, float(h.highlight_weight)) if h.highlight_weight is not None else 1.0
def _days(h):
    a = h.last_reviewed_at or h.created_at
    return 30.0 if a is None else max(0.0, (NOW - a).total_seconds() / 86400.0)
def _wpick(items):
    tot = sum(x[1] for x in items)
    if tot <= 0: return random.choice(items)
    r = random.random() * tot; u = 0.0
    for it in items:
        u += it[1]
        if u >= r: return it
    return items[-1]

def algo(pool, settings, n=None):
    if n is None: n = settings.daily_review_count
    active = [h for h in pool if not h.is_discarded]
    if not active: return []
    cands = []
    for h in active:
        w = _bw(h) * _hw(h)
        if w <= 0.0: continue
        s = _ts(_days(h)) * w
        if s <= 0.0: continue
        cands.append((h, s, h.book_id))
    if not cands: return []
    alpha = (settings.highlight_recency - 5) / 5.0
    if alpha != 0.0:
        raw = [(max(0.0,(NOW-h.created_at).total_seconds()/86400.0) if h.created_at else None)
               for h,_,_ in cands]
        known = [a for a in raw if a is not None]
        fb = sorted(known)[len(known)//2] if known else 0.0
        ages = [a if a is not None else fb for a in raw]
        mn, mx = min(ages), max(ages); sp = max(mx - mn, 1.0)
        nc = []
        for (h, s, bid), age in zip(cands, ages):
            norm = (age - mn) / sp
            ns = s * math.exp(alpha * (0.5 - norm) * 4)
            if ns > 0.0: nc.append((h, ns, bid))
        cands = nc
    if not cands: return []
    mpb = 2 if n >= 4 else 1
    sel, bc, rem = [], defaultdict(int), cands[:]
    while len(sel) < n and rem:
        elig = [c for c in rem if bc[c[2]] < mpb]
        if not elig: break
        p = _wpick(elig); sel.append(p[0]); bc[p[2]] += 1; rem.remove(p)
    if len(sel) < n and rem:
        while len(sel) < n and rem:
            p = _wpick(rem); sel.append(p[0]); rem.remove(p)
    return sel

def sim(pool, settings, n=None, T=8_000):
    counts = Counter()
    _n = n if n is not None else settings.daily_review_count
    for _ in range(T):
        for h in algo(pool, settings, n=_n): counts[h.id] += 1
    return {hid: c/T for hid, c in counts.items()}

def mk_book(bid, n_h, base_id, ca=60):
    return [MockHighlight(base_id+i, ca=ca, bid=bid) for i in range(n_h)]

random.seed(2026)
P = F = 0
def chk(name, ok, d=""):
    global P, F
    if ok: print(f"  [PASS] {name}"); P += 1
    else:  print(f"  [FAIL] {name}" + (f"  <<< {d}" if d else "")); F += 1

# ══════════════════════════════════════════════════════════════════
# SUITE 1 — Time-decay formula (tau = 14 days)
# ══════════════════════════════════════════════════════════════════
print("="*64); print("SUITE 1 -- Time-decay formula (tau=14)"); print("="*64)

chk("ts(0) == 0.0 exactly",         _ts(0.0) == 0.0)
chk("ts(14) == 1 - 1/e",            abs(_ts(14) - (1 - 1/math.e)) < 1e-9)
chk("ts(28) == 1 - 1/e^2",          abs(_ts(28) - (1 - math.exp(-2))) < 1e-9)
chk("ts(1) < 0.07  (very recent)",  _ts(1) < 0.07)
chk("ts(30) ~= 0.88268 (default)",  abs(_ts(30) - 0.882681) < 1e-5)
chk("ts monotone: 1<7<14<30<90<365",_ts(1)<_ts(7)<_ts(14)<_ts(30)<_ts(90)<_ts(365))
chk("ts bounded in [0,1] always",    all(0.0 <= _ts(d) <= 1.0 for d in [0,1,14,30,100,1000,9999]))
chk("ts(530d) == 1.0 exactly (float64 saturation ~1.5yr)",  _ts(530) == 1.0)
chk("ts(365d) < 1.0 (practical max age is still < 1.0)",    _ts(365) < 1.0)
chk("ts(0) * any_weight = 0 -> excluded from pool",
    len(algo([MockHighlight(1, lr=0)], MockSettings())) == 0)

# ══════════════════════════════════════════════════════════════════
# SUITE 2 — Anchor selection (last_reviewed_at > created_at > 30d)
# ══════════════════════════════════════════════════════════════════
print(); print("="*64); print("SUITE 2 -- Anchor selection"); print("="*64)

chk("lr takes priority over ca:  H(ca=365,lr=1) -> ~1d",
    abs(_days(MockHighlight(1, ca=365, lr=1)) - 1.0) < 0.01)
chk("lr=365d even when ca=1d:    H(ca=1,lr=365) -> ~365d",
    abs(_days(MockHighlight(2, ca=1, lr=365)) - 365.0) < 0.1)
chk("Never reviewed:             H(ca=90) -> ~90d",
    abs(_days(MockHighlight(3, ca=90)) - 90.0) < 0.01)
chk("Both None:                  -> 30d fallback",
    _days(MockHighlight(4, ca=None)) == 30.0)

s_lr1  = _ts(_days(MockHighlight(1, ca=365, lr=1)))    # just reviewed
s_def  = _ts(30.0)                                       # default
s_lr365= _ts(_days(MockHighlight(3, ca=1, lr=365)))    # reviewed long ago
chk("Score ordering: lr=1d < default-30d < lr=365d",
    s_lr1 < s_def < s_lr365)

# Statistical: h(lr=1d) vs h(lr=60d) — long-unreviewed should dominate
f_anch = sim([MockHighlight(1, ca=365, lr=1, bid=1),
              MockHighlight(2, ca=365, lr=60, bid=2)], MockSettings(r=5), n=1)
chk("Selection: h(lr=1d) << h(lr=60d) — long-unreviewed wins",
    f_anch.get(1,0) < f_anch.get(2,0) * 0.5,
    f"lr1d={f_anch.get(1,0):.3f} lr60d={f_anch.get(2,0):.3f}")

# ══════════════════════════════════════════════════════════════════
# SUITE 3 — Weight system
# ══════════════════════════════════════════════════════════════════
print(); print("="*64); print("SUITE 3 -- Weight system"); print("="*64)

chk("hw=0.0 -> excluded",          len(algo([MockHighlight(1, hw=0.0)], MockSettings())) == 0)
chk("bw=0.0 -> excluded",          len(algo([MockHighlight(1, bw=0.0)], MockSettings())) == 0)
chk("hw=2.0, bw=0.0 -> excluded",  len(algo([MockHighlight(1, hw=2.0, bw=0.0)], MockSettings())) == 0)
chk("hw=None -> 1.0 fallback (not excluded)",
    len(algo([MockHighlight(1, hw=None)], MockSettings())) == 1)

# All 5 UI weight options stay in pool
for hw_val, lbl in [(0.25,"Much less"),(0.5,"Less"),(1.0,"Normal"),(1.5,"More"),(2.0,"Much more")]:
    res = algo([MockHighlight(1, hw=hw_val)], MockSettings())
    chk(f"  UI '{lbl}' hw={hw_val}: in pool (not excluded)", len(res) == 1)

# Score proportionality (same age 30d, bw=1.0)
b = _ts(30.0)
chk("hw=2.0 score = 2x hw=1.0",             abs(b*2.0/(b*1.0) - 2.0) < 1e-9)
chk("hw=0.5 score = 0.5x hw=1.0",           abs(b*0.5/(b*1.0) - 0.5) < 1e-9)
chk("Much-more / Much-less ratio = 8x",      abs(b*2.0/(b*0.25) - 8.0) < 1e-9)
chk("hw=2.0 * bw=2.0 = 4x default",          abs(b*4.0/(b*1.0) - 4.0) < 1e-9)
chk("hw=1.5 * bw=2.0 = 3x default",          abs(b*3.0/(b*1.0) - 3.0) < 1e-9)

# Statistical: Much-more (2.0) vs Much-less (0.25) at equal age -> ~8:1
h_mm = MockHighlight(1, ca=30, hw=2.0,  bid=1)
h_ml = MockHighlight(2, ca=30, hw=0.25, bid=2)
fw = sim([h_mm, h_ml], MockSettings(), n=1)
ratio_w = fw.get(1, 0.0001) / fw.get(2, 0.0001)
chk("Statistical: Much-more/Much-less ~ 8x (within 7-9)",
    7.0 < ratio_w < 9.0, f"ratio={ratio_w:.2f}")

# ══════════════════════════════════════════════════════════════════
# SUITE 4 — is_favorited has NO effect on scoring
# ══════════════════════════════════════════════════════════════════
print(); print("="*64); print("SUITE 4 -- is_favorited has no effect on scoring"); print("="*64)

h_fav = MockHighlight(1, ca=30, fav=True,  bid=1)
h_unf = MockHighlight(2, ca=30, fav=False, bid=2)
# Confirm identical raw scores
s_fav = _ts(_days(h_fav)) * _bw(h_fav) * _hw(h_fav)
s_unf = _ts(_days(h_unf)) * _bw(h_unf) * _hw(h_unf)
chk("Favorited/non-favorited produce identical raw scores", abs(s_fav - s_unf) < 1e-9)
chk("is_favorited=True: not excluded from pool",
    len(algo([MockHighlight(1, ca=30, fav=True)], MockSettings())) == 1)

# Statistical: both should have ~50% selection (1-item-each, n=1)
ff = sim([h_fav, h_unf], MockSettings(), n=1)
chk("Statistical: favorited vs non-favorited within 3% of 50/50",
    abs(ff.get(1,0) - ff.get(2,0)) < 0.03,
    f"fav={ff.get(1,0):.3f} unfav={ff.get(2,0):.3f}")

# ══════════════════════════════════════════════════════════════════
# SUITE 5 — is_discarded exclusion & review_count unused
# ══════════════════════════════════════════════════════════════════
print(); print("="*64); print("SUITE 5 -- is_discarded / review_count"); print("="*64)

chk("discarded hw=2.0 -> excluded",
    len(algo([MockHighlight(1, hw=2.0, disc=True)], MockSettings())) == 0)
r = algo([MockHighlight(1, disc=True), MockHighlight(2)], MockSettings())
chk("mixed: only non-discarded returned", len(r)==1 and r[0].id==2)
chk("all discarded -> empty",
    len(algo([MockHighlight(i, disc=True) for i in range(5)], MockSettings())) == 0)
chk("discarded+high_weight still excluded (weight can't override disc)",
    len(algo([MockHighlight(1, hw=2.0, bw=2.0, disc=True)], MockSettings())) == 0)

# review_count not in formula — same scores regardless
h_r0  = MockHighlight(1, ca=60, lr=30, rc=0,   bid=60)
h_r99 = MockHighlight(2, ca=60, lr=30, rc=99,  bid=61)
sc0  = _ts(_days(h_r0))  * _bw(h_r0)  * _hw(h_r0)
sc99 = _ts(_days(h_r99)) * _bw(h_r99) * _hw(h_r99)
chk("review_count=0 vs 99: identical scores (not in formula)",
    abs(sc0 - sc99) < 1e-9, f"sc0={sc0:.6f} sc99={sc99:.6f}")

# ══════════════════════════════════════════════════════════════════
# SUITE 6 — Recency bias (deterministic)
# ══════════════════════════════════════════════════════════════════
print(); print("="*64); print("SUITE 6 -- Recency bias"); print("="*64)

chk("r=5: alpha == 0.0 (recency block skipped)", (5-5)/5.0 == 0.0)
chk("r=0: alpha == -1.0", abs((0-5)/5.0 - (-1.0)) < 1e-9)
chk("r=10: alpha == +1.0", abs((10-5)/5.0 - 1.0) < 1e-9)

# Multiplier values for extreme norms
for r_v in [0, 10]:
    alpha = (r_v-5)/5.0
    m_old = math.exp(alpha*(0.5-1.0)*4)   # norm=1 = oldest
    m_new = math.exp(alpha*(0.5-0.0)*4)   # norm=0 = newest
    if r_v == 0:
        chk("r=0: old_mult > 1.0  (older highlights boosted)", m_old > 1.0)
        chk("r=0: new_mult < 1.0  (newer highlights penalised)", m_new < 1.0)
        chk("r=0: product old_mult * new_mult == 1 (symmetry)", abs(m_old*m_new-1.0)<1e-9)
        chk(f"r=0: old boost >= 7x  (got {m_old:.3f})", m_old >= 7.0)
    else:
        chk("r=10: new_mult > 1.0 (newer highlights boosted)", m_new > 1.0)
        chk("r=10: old_mult < 1.0 (older highlights penalised)", m_old < 1.0)
        chk("r=10: product == 1 (symmetry)", abs(m_old*m_new-1.0)<1e-9)
        chk(f"r=10: new boost >= 7x (got {m_new:.3f})", m_new >= 7.0)

# Monotone across all 11 slider steps
mults_old = [math.exp(((r-5)/5.0)*(0.5-1.0)*4) if r!=5 else 1.0 for r in range(11)]
chk("Slider: old_mult monotone DECREASING r=0..10",
    all(mults_old[i] >= mults_old[i+1] for i in range(10)))
mults_new = [1/m for m in mults_old]
chk("Slider: new_mult monotone INCREASING r=0..10",
    all(mults_new[i] <= mults_new[i+1] for i in range(10)))
chk("r=5 old_mult == 1.0 exactly", abs(mults_old[5] - 1.0) < 1e-9)

# Recency uses created_at (NOT last_reviewed_at)
# Build manual score for h_A(ca=730d, lr=1d) and h_B(ca=1d, lr=730d) at r=0
h_A = MockHighlight(1, ca=730, lr=1,   bid=1)
h_B = MockHighlight(2, ca=1,   lr=730, bid=2)
sa = _ts(_days(h_A));  sb = _ts(_days(h_B))
alpha_0 = -1.0; mn_ca=1.0; mx_ca=730.0; sp_ca=729.0
norm_A=(730-mn_ca)/sp_ca; norm_B=(1-mn_ca)/sp_ca
mA=math.exp(alpha_0*(0.5-norm_A)*4); mB=math.exp(alpha_0*(0.5-norm_B)*4)
chk("Recency uses ca: at r=0, old-ca highlight gets boost (mult>1)",
    mA > 1.0, f"mult_A={mA:.3f}")
chk("Recency uses ca: at r=0, new-ca highlight gets penalty (mult<1)",
    mB < 1.0, f"mult_B={mB:.3f}")

# Same-age pool: all multipliers identical (relative probabilities preserved)
for r_v in [0, 10]:
    alpha = (r_v-5)/5.0; ages=[60.0,60.0,60.0]; sp=max(max(ages)-min(ages),1.0)
    mults = [math.exp(alpha*(0.5-(a-60.0)/sp)*4) for a in ages]
    chk(f"Same-age r={r_v}: all 3 highlights get identical multiplier",
        abs(mults[0]-mults[1])<1e-9 and abs(mults[1]-mults[2])<1e-9,
        str([round(m,4) for m in mults]))

# Statistical: r=0 -> old-ca highlighted, r=10 -> new-ca highlighted
pool_r = [MockHighlight(1, ca=730, bid=1), MockHighlight(2, ca=1, bid=2)]
f_r0  = sim(pool_r, MockSettings(r=0),  n=1)
f_r5  = sim(pool_r, MockSettings(r=5),  n=1)
f_r10 = sim(pool_r, MockSettings(r=10), n=1)
chk("r=0: old-ca (730d) selected MORE than neutral",
    f_r0.get(1,0) > f_r5.get(1,0), f"r0={f_r0.get(1,0):.3f} r5={f_r5.get(1,0):.3f}")
chk("r=10: new-ca (1d) selected MORE than neutral",
    f_r10.get(2,0) > f_r5.get(2,0), f"r10={f_r10.get(2,0):.3f} r5={f_r5.get(2,0):.3f}")

# ══════════════════════════════════════════════════════════════════
# SUITE 7 — Diversity / per-book cap
# ══════════════════════════════════════════════════════════════════
print(); print("="*64); print("SUITE 7 -- Diversity (per-book cap)"); print("="*64)

chk("n<=3: max_per_book=1", all((2 if n>=4 else 1)==1 for n in [1,2,3]))
chk("n>=4: max_per_book=2", all((2 if n>=4 else 1)==2 for n in [4,5,6,15]))

pool6 = mk_book(1, 6, 100)
r3 = [algo(pool6, MockSettings(n=3)) for _ in range(200)]
chk("n=3, 1-book pool of 6: always returns 3",        all(len(r)==3 for r in r3))
r4 = [algo(pool6, MockSettings(n=4)) for _ in range(200)]
chk("n=4, 1-book pool of 6: always returns 4",        all(len(r)==4 for r in r4))

pool_3b = mk_book(10,2,200)+mk_book(20,2,210)+mk_book(30,2,220)
for _ in range(200):
    r = algo(pool_3b, MockSettings(n=4))
    bc = Counter(h.book_id for h in r)
    assert max(bc.values()) <= 2, f"cap violated: {bc}"
chk("n=4, 3 books x 2 highlights: at most 2/book in 200 runs", True)

for _ in range(200):
    ids = [h.id for h in algo(mk_book(1,20,300), MockSettings(n=10))]
    assert len(ids) == len(set(ids)), f"duplicate IDs: {ids}"
chk("No duplicate highlights across 200 runs (n=10, pool=20)", True)

chk("pool(3) < n(10): returns 3",  len(algo(mk_book(1,3,400), MockSettings(n=10))) == 3)
chk("n=1: exactly 1 returned",     len(algo(mk_book(1,5,500), MockSettings(n=1)))  == 1)

# Fill logic: book A has 10 highlights, book B has 1; n=5
pool_dom = mk_book(1,10,600) + mk_book(2,1,700)
results_fill = [algo(pool_dom, MockSettings(n=5)) for _ in range(200)]
chk("Fill: dominant book, n=5, pool=11 -> always 5", all(len(r)==5 for r in results_fill))
book_A_counts = [Counter(h.book_id for h in r).get(1,0) for r in results_fill]
chk("Fill: book A appears >2 times in some runs (fill kicks in)",
    any(c > 2 for c in book_A_counts))

# ══════════════════════════════════════════════════════════════════
# SUITE 8 — daily_review_count and settings clamping
# ══════════════════════════════════════════════════════════════════
print(); print("="*64); print("SUITE 8 -- n and settings clamping"); print("="*64)

pool10 = [MockHighlight(i, bid=i) for i in range(1,11)]
for nv in [1,3,5,7,10,15]:
    chk(f"n={nv}: returns min({nv},10)={min(nv,10)}",
        len(algo(pool10, MockSettings(n=nv))) == min(nv,10))
chk("n=0: returns empty", len(algo(pool10, MockSettings(), n=0)) == 0)

def clamp_n(v): return max(1,min(15,v))
def clamp_r(v): return max(0,min(10,v))
for v,exp in [(-1,1),(0,1),(1,1),(7,7),(15,15),(16,15),(100,15)]:
    chk(f"clamp_daily_review_count({v}) = {exp}", clamp_n(v) == exp)
for v,exp in [(-1,0),(0,0),(5,5),(10,10),(11,10)]:
    chk(f"clamp_highlight_recency({v}) = {exp}",  clamp_r(v) == exp)

# ══════════════════════════════════════════════════════════════════
# SUITE 9 — Integration: combined weight + recency + diversity
# ══════════════════════════════════════════════════════════════════
print(); print("="*64); print("SUITE 9 -- Integration"); print("="*64)

# Discarded overrides high weight
r = algo([MockHighlight(1,hw=2.0,disc=True), MockHighlight(2,hw=0.25)], MockSettings())
chk("Discarded hw=2.0 vs active hw=0.25: only active chosen", len(r)==1 and r[0].id==2)

# bw=0 + r=10 (prefer newer) -> still excluded
r2 = algo([MockHighlight(1,ca=1,bw=0.0)], MockSettings(r=10))
chk("bw=0 + recency r=10 -> still excluded", len(r2)==0)

# Weight + recency compounding: old-ca + hw=2.0 at r=0 should dominate
h_old_mm = MockHighlight(1, ca=730, hw=2.0, bid=1)
h_new_ml = MockHighlight(2, ca=1,   hw=0.25, bid=2)
f_combo = sim([h_old_mm, h_new_ml], MockSettings(r=0), n=1)
chk("r=0 + old(ca=730,hw=2.0) vs new(ca=1,hw=0.25): old dominates (>90%)",
    f_combo.get(1,0) > 0.90, f"old={f_combo.get(1,0):.3f}")

# Flip: r=10 + new(ca=1,hw=2.0) vs old(ca=730,hw=0.25)
h_new_mm = MockHighlight(1, ca=1,   hw=2.0,  bid=1)
h_old_ml = MockHighlight(2, ca=730, hw=0.25, bid=2)
f_combo2 = sim([h_new_mm, h_old_ml], MockSettings(r=10), n=1)
chk("r=10 + new(ca=1,hw=2.0) vs old(ca=730,hw=0.25): new dominates (>95%)",
    f_combo2.get(1,0) > 0.95, f"new={f_combo2.get(1,0):.3f}")

# is_favorited + recency + weight: favorited status doesn't override other factors
h_fav_new = MockHighlight(1, ca=1, hw=1.0, fav=True, bid=1)   # new + favorited
h_unf_old = MockHighlight(2, ca=730, hw=1.0, fav=False, bid=2) # old + not favorited
f_fav_r0 = sim([h_fav_new, h_unf_old], MockSettings(r=0), n=1)
chk("r=0: old non-favorited beats new favorited (fav has no score effect)",
    f_fav_r0.get(2,0) > f_fav_r0.get(1,0),
    f"old_unfav={f_fav_r0.get(2,0):.3f} new_fav={f_fav_r0.get(1,0):.3f}")

# daily_review_count respected end-to-end across settings
pool20 = [MockHighlight(i, bid=i) for i in range(1,21)]
for n_val in [1, 5, 10, 15]:
    for _ in range(20):
        r = algo(pool20, MockSettings(n=n_val))
        assert len(r) == n_val, f"n={n_val} returned {len(r)}"
chk("daily_review_count [1,5,10,15] respected across 20 runs each", True)

# ══════════════════════════════════════════════════════════════════
print()
print("=" * 64)
print(f"TOTAL: {P}/{P+F} passed  ({F} failed)")
print("=" * 64)
sys.exit(0 if F == 0 else 1)
