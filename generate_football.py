#!/usr/bin/env python3
"""
Football contribution animation generator for GitHub profile README.
Reads GitHub contribution data via GraphQL API and generates an SVG where
a cartoon developer character kicks a football through each committed square.
"""

import os
import sys
import math
import requests

# ── Layout constants ──────────────────────────────────────────────────────────
CELL_SIZE   = 11        # contribution square size (px)
CELL_GAP    = 2         # gap between squares
CELL_STEP   = CELL_SIZE + CELL_GAP
GRID_X      = 100       # grid left edge (leaves room for character on left)
GRID_Y      = 30        # grid top edge (leaves room for month labels)
NUM_ROWS    = 7         # days per week (Sun-Sat)
CHAR_X      = 50        # character's X center
FOOTER_H    = 22        # space below grid for footer text

# Contribution level fill colors (dark theme, GitHub-style)
LEVEL_COLORS = [
    "#161b22",  # 0 = no commits
    "#0e4429",  # 1 = 1-2 commits
    "#006d32",  # 2 = 3-5
    "#26a641",  # 3 = 6-10
    "#39d353",  # 4 = 10+
]

def contribution_level(count: int) -> int:
    if count == 0: return 0
    if count <= 2: return 1
    if count <= 5: return 2
    if count <= 10: return 3
    return 4

def cell_center(week_idx: int, day_idx: int) -> tuple[float, float]:
    x = GRID_X + week_idx * CELL_STEP + CELL_SIZE / 2
    y = GRID_Y + day_idx  * CELL_STEP + CELL_SIZE / 2
    return x, y

# ── GitHub API ────────────────────────────────────────────────────────────────
def get_contributions(username: str, token: str) -> tuple[list, int]:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
      }
    }
    """
    resp = requests.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"bearer {token}"},
        json={"query": query, "variables": {"login": username}},
        timeout=15,
    )
    resp.raise_for_status()
    cal = resp.json()["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    return cal["weeks"], cal["totalContributions"]

# ── SVG path builder ──────────────────────────────────────────────────────────
def build_ball_path(start: tuple, commit_points: list) -> str:
    """
    Build an SVG path string of quadratic Bezier arcs from start position
    through each committed square, then back to start. The arc height scales
    with distance so short hops look like chips and long ones look like shots.
    """
    if not commit_points:
        return f"M {start[0]:.1f},{start[1]:.1f}"

    waypoints = [start] + commit_points + [start]
    parts = [f"M {waypoints[0][0]:.1f},{waypoints[0][1]:.1f}"]

    for i in range(1, len(waypoints)):
        x1, y1 = waypoints[i - 1]
        x2, y2 = waypoints[i]
        dist    = math.hypot(x2 - x1, y2 - y1)
        # Arc height: taller for longer distances (looks more like a kicked ball)
        arc_h   = min(40, max(10, dist * 0.38))
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2 - arc_h
        parts.append(f"Q {mx:.1f},{my:.1f} {x2:.1f},{y2:.1f}")

    return " ".join(parts)

# ── SVG components ────────────────────────────────────────────────────────────
def character_svg(cx: int, cy: int) -> str:
    """
    Stick figure with glasses in a kicking pose.
    Character is positioned so the foot aligns roughly with the ball start.
    """
    s  = "#606060"   # stroke color
    sw = 1.8         # stroke width
    hy = cy - 30     # head center Y

    return f"""
  <!-- ── Cartoon developer in kicking pose ── -->
  <g stroke="{s}" stroke-width="{sw}" stroke-linecap="round" fill="none">

    <!-- Head -->
    <circle cx="{cx}" cy="{hy}" r="8.5" fill="#1a1a1a" stroke="{s}" stroke-width="{sw}"/>

    <!-- Glasses (nerd points) -->
    <circle cx="{cx - 3}" cy="{hy - 1}" r="2.7" stroke="#888" stroke-width="0.9"/>
    <circle cx="{cx + 3}" cy="{hy - 1}" r="2.7" stroke="#888" stroke-width="0.9"/>
    <line   x1="{cx - 0.3}" y1="{hy - 1}" x2="{cx + 0.3}" y2="{hy - 1}" stroke="#888" stroke-width="0.8"/>
    <line   x1="{cx - 9}"   y1="{hy - 1}" x2="{cx - 5.7}" y2="{hy - 1}" stroke="#888" stroke-width="0.8"/>
    <line   x1="{cx + 5.7}" y1="{hy - 1}" x2="{cx + 9}"   y2="{hy - 1}" stroke="#888" stroke-width="0.8"/>

    <!-- Eyes inside glasses -->
    <circle cx="{cx - 3}" cy="{hy - 1}" r="1.2" fill="{s}" stroke="none"/>
    <circle cx="{cx + 3}" cy="{hy - 1}" r="1.2" fill="{s}" stroke="none"/>

    <!-- Smirk -->
    <path d="M {cx - 3},{hy + 3} Q {cx},{hy + 6} {cx + 3},{hy + 3}" stroke-width="1"/>

    <!-- Hair tuft -->
    <path d="M {cx - 5},{hy - 8} Q {cx},{hy - 13} {cx + 5},{hy - 8}" stroke="#555" stroke-width="2.2"/>

    <!-- Body -->
    <line x1="{cx}"      y1="{hy + 9}"   x2="{cx}"      y2="{cy - 5}"/>

    <!-- Arms: left arm back (balance), right arm forward -->
    <line x1="{cx}"      y1="{hy + 14}"  x2="{cx - 12}"  y2="{hy + 20}"/>
    <line x1="{cx}"      y1="{hy + 14}"  x2="{cx + 8}"   y2="{hy + 19}"/>

    <!-- Standing leg (left) -->
    <line x1="{cx}"      y1="{cy - 5}"   x2="{cx - 4}"   y2="{cy + 12}"/>
    <line x1="{cx - 4}"  y1="{cy + 12}"  x2="{cx - 8}"   y2="{cy + 17}" stroke-width="1.3"/>

    <!-- Kicking leg (right, extended forward) -->
    <line x1="{cx}"      y1="{cy - 5}"   x2="{cx + 16}"  y2="{cy + 2}"/>

    <!-- Boot at end of kicking leg -->
    <ellipse cx="{cx + 21}" cy="{cy + 2}" rx="6" ry="3.5" fill="#1a1a1a" stroke="{s}" stroke-width="1.3"/>

  </g>"""


def football_svg() -> str:
    """A football (soccer ball) as inline SVG shapes."""
    return """
  <!-- ── Football ── (rotate="auto" makes it spin along the arc) -->
  <g>
    <circle r="5.5" fill="#e8e8e8" stroke="#555" stroke-width="0.8"/>
    <!-- Pentagon mark -->
    <path d="M0,-3.5 L3.3,1.1 L2,4.5 L-2,4.5 L-3.3,1.1 Z"
          fill="none" stroke="#555" stroke-width="0.6" opacity="0.55"/>
    <!-- Centre dot -->
    <circle r="1.5" fill="#555" opacity="0.35"/>"""


def month_labels_svg(weeks: list) -> str:
    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
              "Jul","Aug","Sep","Oct","Nov","Dec"]
    labels    = []
    prev_month = None
    for wi, week in enumerate(weeks):
        if not week["contributionDays"]:
            continue
        m = int(week["contributionDays"][0]["date"].split("-")[1]) - 1
        if m != prev_month:
            x = GRID_X + wi * CELL_STEP
            labels.append(
                f'<text x="{x}" y="{GRID_Y - 6}" fill="#2d2d2d" '
                f'font-size="7" font-family="\'JetBrains Mono\',monospace">'
                f'{MONTHS[m]}</text>'
            )
            prev_month = m
    return "\n  ".join(labels)


def grid_cells_svg(weeks: list) -> str:
    cells = []
    for wi, week in enumerate(weeks):
        for di, day in enumerate(week["contributionDays"]):
            x = GRID_X + wi * CELL_STEP
            y = GRID_Y + di * CELL_STEP
            c = LEVEL_COLORS[contribution_level(day["contributionCount"])]
            cells.append(
                f'<rect x="{x}" y="{y}" width="{CELL_SIZE}" height="{CELL_SIZE}" '
                f'rx="2" fill="{c}" stroke="#0d1117" stroke-width="0.4"/>'
            )
    return "\n  ".join(cells)

# ── Main SVG generation ───────────────────────────────────────────────────────
def generate_svg(weeks: list, total: int, output_path: str) -> None:
    num_weeks = len(weeks)

    # Canvas dimensions
    svg_w = GRID_X + num_weeks * CELL_STEP + 12
    svg_h = GRID_Y + NUM_ROWS  * CELL_STEP + FOOTER_H

    # Character position: vertically centered to the grid
    char_y = GRID_Y + (NUM_ROWS * CELL_STEP) // 2 + 10
    char_x = CHAR_X

    # Ball starts at the tip of the boot
    ball_start = (char_x + 21, char_y + 2)

    # Collect committed squares in chronological order
    commits = []
    for wi, week in enumerate(weeks):
        for di, day in enumerate(week["contributionDays"]):
            if day["contributionCount"] > 0:
                cx, cy = cell_center(wi, di)
                commits.append((cx, cy))

    ball_path = build_ball_path(ball_start, commits)

    # Animation duration: ~0.07 s per committed square, capped between 8 s and 22 s
    dur = max(8.0, min(22.0, len(commits) * 0.07))

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
  width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">

  <!-- Background -->
  <rect width="{svg_w}" height="{svg_h}" fill="#0d1117"/>

  <!-- Month labels -->
  {month_labels_svg(weeks)}

  <!-- Contribution grid -->
  {grid_cells_svg(weeks)}

  <!-- Character -->
  {character_svg(char_x, char_y)}

  <!-- Ball path stored in defs -->
  <defs>
    <path id="bp" d="{ball_path}"/>
  </defs>

  <!-- Animated football -->
  {football_svg()}
    <animateMotion dur="{dur:.1f}s" repeatCount="indefinite" rotate="auto">
      <mpath href="#bp"/>
    </animateMotion>
  </g>

  <!-- Footer -->
  <text x="{svg_w // 2}" y="{svg_h - 5}" text-anchor="middle"
    fill="#222222" font-size="8" font-family="'JetBrains Mono',monospace" letter-spacing="1">
    {total} contributions · still building
  </text>

</svg>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"✓ {output_path} generated — {len(commits)} commits animated, {dur:.1f}s loop")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    token    = os.environ.get("GITHUB_TOKEN", "")
    username = os.environ.get("USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER", "")

    if not token or not username:
        print("Error: GITHUB_TOKEN and USERNAME environment variables are required.")
        sys.exit(1)

    print(f"Fetching contributions for {username}...")
    weeks, total = get_contributions(username, token)
    generate_svg(weeks, total, "football.svg")


if __name__ == "__main__":
    main()
