#!/usr/bin/env python3
"""
Football contribution animation v3.
- Minecraft pixel-art character (jersey, boots, glasses) with SMIL kick animation
- Proper soccer ball (pentagon + spokes) that spins along arc and vanishes on landing
- First half of year: statically shown
- Second half: starts dark; character kicks the LAST 20 committed squares into view,
  one per kick, then loops
"""

import os, sys, math, json
import urllib.request
import urllib.parse
import urllib.error


# ── Layout ────────────────────────────────────────────────────────────────────
CELL        = 11          # contribution square size
GAP         = 2           # gap between squares
STEP        = CELL + GAP
GRID_X      = 104         # left edge of grid (space for character)
GRID_Y      = 28          # top edge (space for month labels)
ROWS        = 7
HALF        = 26          # weeks 0-25 = first half (shown), 26+ = second half
MAX_KICKS   = 20          # animate only the last N committed squares in second half

# ── Timing ────────────────────────────────────────────────────────────────────
START_PAUSE  = 1.5        # pause before first kick (s)
KICK_TOTAL   = 1.4        # total time per kick cycle (s)
FLIGHT_FRAC  = 0.60       # fraction of KICK_TOTAL the ball is in the air
END_PAUSE    = 1.5        # hold at end before loop restarts

# ── Colors ────────────────────────────────────────────────────────────────────
SKIN    = "#c68642"
JERSEY  = "#1565c0"   # navy blue jersey
JSTRIPE = "#1e88e5"   # lighter stripe
JNUM    = "#ffffff"
PANTS   = "#212121"
BOOT    = "#303030"
LCOLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

def lv(c):
    return 0 if c == 0 else 1 if c <= 2 else 2 if c <= 5 else 3 if c <= 10 else 4

def cell_center(wi, di):
    return GRID_X + wi * STEP + CELL / 2, GRID_Y + di * STEP + CELL / 2

# ── GitHub API / Fallback Data ────────────────────────────────────────────────
def get_data(username, token):
    if token and username:
        try:
            q = ("query($l:String!){user(login:$l){contributionsCollection{"
                 "contributionCalendar{totalContributions "
                 "weeks{contributionDays{contributionCount date}}}}}}")
            req_data = json.dumps({"query": q, "variables": {"login": username}}).encode("utf-8")
            req = urllib.request.Request(
                "https://api.github.com/graphql",
                data=req_data,
                headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "Python"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
                return cal["weeks"], cal["totalContributions"]
        except Exception as e:
            print(f"GraphQL API failed ({e}), trying public fallback...")

    # Public API fallback for local testing without token
    user = urllib.parse.quote(username or "romannihal")
    try:
        req = urllib.request.Request(
            f"https://github-contributions-api.jogruber.de/v4/{user}?y=last",
            headers={"User-Agent": "Python"}
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            total = data.get("total", {}).get("lastYear", 365)
            raw_contribs = data.get("contributions", [])
            
            # Group by weeks (7 days per week)
            weeks = []
            current_week = []
            for d in raw_contribs:
                current_week.append({
                    "contributionCount": d["count"],
                    "date": d["date"]
                })
                if len(current_week) == 7:
                    weeks.append({"contributionDays": current_week})
                    current_week = []
            if current_week:
                weeks.append({"contributionDays": current_week})
            return weeks, total
    except Exception as e:
        print(f"Public API failed ({e}), generating synthetic mock data for preview...")
        import random
        random.seed(42)
        weeks = []
        total = 0
        for w in range(52):
            days = []
            for d in range(7):
                cnt = random.choice([0, 0, 0, 1, 3, 5, 8, 12]) if w > 20 else random.choice([0, 0, 1, 2])
                total += cnt
                days.append({"contributionCount": cnt, "date": f"2026-01-{d+1:02d}"})
            weeks.append({"contributionDays": days})
        return weeks, total



# ── Arc control point ─────────────────────────────────────────────────────────
def arc_cp(x1, y1, x2, y2):
    d = math.hypot(x2 - x1, y2 - y1)
    h = min(45, max(14, d * 0.42))
    return (x1 + x2) / 2, (y1 + y2) / 2 - h

# ── Minecraft character ───────────────────────────────────────────────────────
def char_svg(cx, top):
    """
    Pixel-art Minecraft character in kicking pose.
    Returns (svg_string, boot_tip_x, boot_tip_y, leg_pivot_x, leg_pivot_y).
    All coordinates in global SVG space.
    """
    B = 2  # pixels per Minecraft block

    # Derived positions (all global SVG coords)
    hx, hy    = cx - 4*B, top            # head top-left
    bx, by    = cx - 4*B, top + 8*B      # body top-left
    lax, lay  = bx - 3*B, by             # left arm top-left
    rax, ray  = bx + 8*B, by             # right arm top-left
    llx, lly  = bx, by + 12*B            # left leg top-left
    rlx, rly  = bx + 4*B, by + 12*B     # right leg top-left (pivot top-left)

    boot_h    = 3*B                       # boot height
    leg_h     = 12*B                      # leg height

    # Leg bounding box for animateTransform pivot:
    # pivot at top-center of right leg = (rlx + 2*B, rly) in global coords
    # but animateTransform rotate values use element-local coords.
    # The right leg group will be positioned at transform="translate(rlx,rly)"
    # so the local pivot is (2*B, 0) = (4, 0)
    piv_local_x = 2*B   # = 4  (centre of 4*B wide leg)
    piv_local_y = 0

    # Boot tip at kick peak — approximate for ball launch point.
    # At peak rotate 55deg around (4, 0):
    # boot right edge local: (5*B, leg_h + boot_h) = (10, 30)
    bx_l, by_l = 5*B - piv_local_x, leg_h + boot_h - piv_local_y   # = (6, 30)
    angle_rad  = math.radians(55)
    kick_bx    = bx_l * math.cos(angle_rad) + by_l * math.sin(angle_rad) + piv_local_x
    kick_by    = -bx_l * math.sin(angle_rad) + by_l * math.cos(angle_rad) + piv_local_y
    boot_tip_x = llx + kick_bx
    boot_tip_y = lly + kick_by

    s = f"""
  <!-- ═══ Minecraft character ═══ -->

  <!-- Head (8×8 blocks) -->
  <rect x="{hx}"       y="{hy}"      width="{8*B}" height="{8*B}" fill="{SKIN}"/>
  <!-- Hair / dark cap top -->
  <rect x="{hx}"       y="{hy}"      width="{8*B}" height="{2*B}" fill="#3d1f08"/>
  <rect x="{hx+B}"     y="{hy+2*B}"  width="{B}"   height="{B}"   fill="#3d1f08"/>
  <rect x="{hx+6*B}"   y="{hy+2*B}"  width="{B}"   height="{B}"   fill="#3d1f08"/>
  <!-- Glasses (nerd accent) -->
  <rect x="{hx+B}"     y="{hy+2*B}"  width="{3*B}" height="{2*B}" fill="none" stroke="#aaa" stroke-width="0.6"/>
  <rect x="{hx+4*B}"   y="{hy+2*B}"  width="{3*B}" height="{2*B}" fill="none" stroke="#aaa" stroke-width="0.6"/>
  <line x1="{hx+4*B}"  y1="{hy+3*B}" x2="{hx+4*B}" y2="{hy+3*B}" stroke="#aaa" stroke-width="0.5"/>
  <!-- Eyes inside glasses -->
  <rect x="{hx+B}"     y="{hy+3*B}"  width="{2*B}" height="{B}"   fill="#1a1a1a"/>
  <rect x="{hx+5*B}"   y="{hy+3*B}"  width="{2*B}" height="{B}"   fill="#1a1a1a"/>
  <!-- Mouth -->
  <rect x="{hx+2*B}"   y="{hy+6*B}"  width="{B}"   height="{B}"   fill="#7a3b2a"/>
  <rect x="{hx+5*B}"   y="{hy+6*B}"  width="{B}"   height="{B}"   fill="#7a3b2a"/>

  <!-- Body (jersey: 8×12 blocks) -->
  <rect x="{bx}"       y="{by}"      width="{8*B}" height="{12*B}" fill="{JERSEY}"/>
  <!-- Collar -->
  <rect x="{bx+3*B}"   y="{by}"      width="{2*B}" height="{B}"    fill="{JSTRIPE}"/>
  <!-- Chest stripe -->
  <rect x="{bx}"       y="{by+5*B}"  width="{8*B}" height="{2*B}"  fill="{JSTRIPE}" opacity="0.55"/>
  <!-- Jersey number (two vertical bars for "7" silhouette) -->
  <rect x="{bx+3*B}"   y="{by+2*B}"  width="{2*B}" height="{B}"   fill="{JNUM}" opacity="0.45"/>
  <rect x="{bx+4*B}"   y="{by+2*B}"  width="{B}"   height="{4*B}" fill="{JNUM}" opacity="0.45"/>

  <!-- Left arm: swings back for balance -->
  <g transform="translate({lax},{lay}) rotate(22,{3*B//2},0)">
    <rect x="0" y="0" width="{3*B}" height="{10*B}" fill="{JERSEY}"/>
    <rect x="0" y="{9*B}" width="{3*B}" height="{2*B}" fill="{SKIN}"/>
  </g>

  <!-- Right arm: swings forward -->
  <g transform="translate({rax},{ray}) rotate(-22,{3*B//2},0)">
    <rect x="0" y="0" width="{3*B}" height="{10*B}" fill="{JERSEY}"/>
    <rect x="0" y="{9*B}" width="{3*B}" height="{2*B}" fill="{SKIN}"/>
  </g>

  <!-- Left leg (anatomically, on the right side of screen - static, standing) -->
  <rect x="{rlx}"      y="{rly}"     width="{4*B}" height="{leg_h}" fill="{PANTS}"/>
  <!-- Left boot (pointing to the right) -->
  <rect x="{rlx}"      y="{rly+leg_h}" width="{5*B}" height="{boot_h}" fill="{BOOT}"/>

  <!-- Right leg + boot — animated via animateTransform (kicks forward) -->
  <g transform="translate({llx},{lly})">
    <g id="rleg">
      <rect x="0" y="0"           width="{4*B}" height="{leg_h}"  fill="{PANTS}"/>
      <!-- Boot extends one block to the right of leg -->
      <rect x="0" y="{leg_h}"    width="{5*B}" height="{boot_h}"  fill="{BOOT}"/>
    </g>
  </g>"""


    return s, boot_tip_x, boot_tip_y, piv_local_x, piv_local_y

# ── Kick animateTransform ─────────────────────────────────────────────────────
def kick_animate_transform(N, tdur, piv_x, piv_y):
    """
    SMIL animateTransform on #rleg. Each kick cycle:
      rest → wind-back (-15 deg) → kick peak (+55 deg) → follow-through (+20) → rest
    """
    vals, kts = [], []

    def add(t, deg):
        vals.append(f"{deg} {piv_x} {piv_y}")
        kts.append(f"{t/tdur:.4f}")

    # Initial rest
    add(0.0, 0)

    for i in range(N):
        t0   = START_PAUSE + i * KICK_TOTAL
        twu  = t0 + KICK_TOTAL * 0.10   # wind-up (slight backward)
        tpk  = t0 + KICK_TOTAL * 0.25   # peak forward kick
        tft  = t0 + KICK_TOTAL * 0.50   # follow-through
        tend = t0 + KICK_TOTAL * 0.75   # return to rest
        tnxt = t0 + KICK_TOTAL - 0.06   # hold rest until next kick

        add(t0,   0)
        add(twu,  15)   # wind back (positive is clockwise/left)
        add(tpk, -55)   # kick! (negative is counterclockwise/right)
        add(tft, -20)   # follow-through
        add(tend,  0)   # return
        if i < N - 1:
            add(tnxt, 0)    # hold rest


    # Final rest
    add(tdur, 0)

    vals_str = "; ".join(vals)
    kts_str  = "; ".join(kts)

    return (f'<animateTransform attributeName="transform" type="rotate" '
            f'values="{vals_str}" '
            f'keyTimes="{kts_str}" '
            f'calcMode="spline" '
            f'keySplines="{"; ".join(["0.4 0 0.6 1"] * (len(kts) - 1))}" '
            f'dur="{tdur:.2f}s" repeatCount="indefinite" additive="replace"/>')

# ── Soccer ball group ─────────────────────────────────────────────────────────
def ball_svg(i, bx, by, tx, ty, p_appear, p_land, p_vanish, tdur):
    """One soccer ball: arcs from boot to target, spins, vanishes on landing."""
    cx, cy = arc_cp(bx, by, tx, ty)
    eps    = 0.003
    path   = f"M{bx:.1f},{by:.1f} Q{cx:.1f},{cy:.1f} {tx:.1f},{ty:.1f}"

    # Opacity keyTimes/values: invisible → visible during flight → gone
    op_kt = (f"0; {max(0, p_appear - eps):.4f}; {p_appear:.4f}; "
             f"{p_land:.4f}; {min(1.0, p_vanish):.4f}; 1")
    op_v  = "0; 0; 1; 1; 0; 0"

    # Motion keyPoints / keyTimes: stay at start, travel, stay at end
    mot_kt = f"0; {p_appear:.4f}; {p_land:.4f}; 1"
    mot_kp = "0; 0; 1; 1"

    return f"""
  <!-- ─ Ball {i} ─ -->
  <g>
    <circle r="5.5" fill="#eeeeee" stroke="#3a3a3a" stroke-width="0.8"/>
    <!-- Central pentagon -->
    <polygon points="0,-3.8 3.6,-1.2 2.2,3.2 -2.2,3.2 -3.6,-1.2"
             fill="#111111" opacity="0.78"/>
    <!-- Spokes from pentagon corners to ball edge -->
    <line x1="0"    y1="-3.8" x2="0"    y2="-5.5" stroke="#777" stroke-width="0.45"/>
    <line x1="3.6"  y1="-1.2" x2="5.3"  y2="-1.8" stroke="#777" stroke-width="0.45"/>
    <line x1="2.2"  y1="3.2"  x2="3.3"  y2="5.0"  stroke="#777" stroke-width="0.45"/>
    <line x1="-2.2" y1="3.2"  x2="-3.3" y2="5.0"  stroke="#777" stroke-width="0.45"/>
    <line x1="-3.6" y1="-1.2" x2="-5.3" y2="-1.8" stroke="#777" stroke-width="0.45"/>
    <!-- Opacity animation -->
    <animate attributeName="opacity"
             values="{op_v}" keyTimes="{op_kt}"
             calcMode="discrete"
             dur="{tdur:.2f}s" repeatCount="indefinite"/>
    <!-- Arc motion + spin -->
    <animateMotion path="{path}"
                   keyPoints="{mot_kp}" keyTimes="{mot_kt}"
                   calcMode="linear"
                   rotate="auto"
                   dur="{tdur:.2f}s" repeatCount="indefinite"/>
  </g>"""

# ── Main SVG generation ───────────────────────────────────────────────────────
def generate(weeks, total, outfile):
    nw    = len(weeks)
    svg_w = GRID_X + nw * STEP + 12
    svg_h = GRID_Y + ROWS * STEP + 20

    # ── Character placement (vertically centred) ──────────────────────────────
    B        = 2
    char_h   = (8 + 12 + 12 + 3) * B   # 70 px
    char_cx  = GRID_X // 2 + 4
    char_top = GRID_Y + (ROWS * STEP - char_h) // 2
    char, boot_x, boot_y, piv_x, piv_y = char_svg(char_cx, char_top)

    # ── Collect second-half commits, pick last MAX_KICKS ─────────────────────
    all_second = []
    for wi in range(HALF, len(weeks)):
        for di, day in enumerate(weeks[wi]["contributionDays"]):
            if day["contributionCount"] > 0:
                cx2, cy2 = cell_center(wi, di)
                all_second.append((wi, di, cx2, cy2, day["contributionCount"]))

    animated = all_second[-MAX_KICKS:]   # last N committed squares
    animated_keys = {(wi, di) for wi, di, *_ in animated}

    N     = len(animated)
    tdur  = START_PAUSE + N * KICK_TOTAL + END_PAUSE   # total loop duration

    # ── Grid cells ─────────────────────────────────────────────────────────────
    # Build index for animated squares
    anim_idx = {(wi, di): i for i, (wi, di, *_) in enumerate(animated)}

    cell_parts = []
    for wi, week in enumerate(weeks):
        for di, day in enumerate(week["contributionDays"]):
            x   = GRID_X + wi * STEP
            y   = GRID_Y + di * STEP
            cnt = day["contributionCount"]
            color = LCOLORS[lv(cnt)]

            if wi < HALF:
                # First half: static
                cell_parts.append(
                    f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                    f'rx="2" fill="{color}"/>'
                )
            elif (wi, di) not in animated_keys:
                # Second half, not animated: static (already committed or empty)
                cell_parts.append(
                    f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                    f'rx="2" fill="{color}"/>'
                )
            else:
                # Second half, ANIMATED: starts dark → lights up when ball lands
                idx      = anim_idx[(wi, di)]
                t_land   = START_PAUSE + idx * KICK_TOTAL + KICK_TOTAL * FLIGHT_FRAC
                p_reveal = t_land / tdur
                p_reset  = (tdur - 0.4) / tdur   # go dark just before loop restarts
                eps      = 0.003
                cell_parts.append(
                    f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                    f'rx="2" fill="{LCOLORS[0]}">'
                    f'<animate attributeName="fill" '
                    f'values="{LCOLORS[0]};{LCOLORS[0]};{color};{color};{LCOLORS[0]}" '
                    f'keyTimes="0;{p_reveal - eps:.4f};{p_reveal:.4f};{p_reset:.4f};1" '
                    f'calcMode="discrete" '
                    f'dur="{tdur:.2f}s" repeatCount="indefinite"/>'
                    f'</rect>'
                )

    cells = "\n  ".join(cell_parts)

    # ── Balls ──────────────────────────────────────────────────────────────────
    ball_parts = []
    for i, (wi, di, tx, ty, _) in enumerate(animated):
        t_appear = START_PAUSE + i * KICK_TOTAL + KICK_TOTAL * 0.22  # appear at kick peak
        t_land   = START_PAUSE + i * KICK_TOTAL + KICK_TOTAL * FLIGHT_FRAC
        t_vanish = t_land + 0.15

        ball_parts.append(ball_svg(
            i, boot_x, boot_y, tx, ty,
            t_appear / tdur, t_land / tdur, t_vanish / tdur, tdur
        ))

    balls = "\n".join(ball_parts)

    # ── Month labels ────────────────────────────────────────────────────────────
    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
              "Jul","Aug","Sep","Oct","Nov","Dec"]
    month_parts, pm = [], None
    for wi, week in enumerate(weeks):
        if week["contributionDays"]:
            m = int(week["contributionDays"][0]["date"].split("-")[1]) - 1
            if m != pm:
                x = GRID_X + wi * STEP
                month_parts.append(
                    f'<text x="{x}" y="{GRID_Y - 7}" fill="#2a2a2a" '
                    f'font-size="7" font-family="monospace">{MONTHS[m]}</text>'
                )
                pm = m

    months = "\n  ".join(month_parts)

    # ── Kick animation ─────────────────────────────────────────────────────────
    kick_anim = kick_animate_transform(N, tdur, piv_x, piv_y)

    # ── Assemble SVG ───────────────────────────────────────────────────────────
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
  width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">

  <!-- Background -->
  <rect width="{svg_w}" height="{svg_h}" fill="#0d1117"/>

  <!-- Month labels -->
  {months}

  <!-- Contribution grid -->
  {cells}

  <!-- Minecraft character with kicking leg -->
  {char}
  <!-- Kick animation applied to right leg inside its parent group -->
  <style>
    #rleg {{ /* fallback target for CSS if SMIL doesn't fire */ }}
  </style>

  <!-- animateTransform lives inside #rleg itself for SMIL compliance -->
  <!-- (injected via the char string above; see kick_animate_transform below) -->

  <!-- Balls (one per animated commit) -->
  {balls}

  <!-- Footer -->
  <text x="{svg_w // 2}" y="{svg_h - 4}" text-anchor="middle"
    fill="#1e1e1e" font-size="8" font-family="monospace" letter-spacing="1">
    {total} contributions this year
  </text>

</svg>"""

    # Inject animateTransform inside the #rleg group
    # We look for the closing </g> that is the #rleg group and inject before it
    svg = svg.replace(
        '<g id="rleg">\n      <rect x="0" y="0"',
        f'<g id="rleg">\n      {kick_anim}\n      <rect x="0" y="0"'
    )

    with open(outfile, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"[+] {outfile} generated - {len(all_second)} second-half commits, "
          f"animating last {N}, loop={tdur:.1f}s")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    token    = os.environ.get("GITHUB_TOKEN", "")
    username = (os.environ.get("USERNAME") or
                os.environ.get("GITHUB_REPOSITORY_OWNER", "") or "romannihal")
    if not token:
        print("Note: GITHUB_TOKEN not set. Running with fallback API / mock preview mode...")
    print(f"Fetching contributions for @{username}…")
    weeks, total = get_data(username, token)
    generate(weeks, total, "football_animation.svg")


if __name__ == "__main__":
    main()

