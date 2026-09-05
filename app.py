import streamlit as st
import re
from datetime import datetime, timedelta
from collections import defaultdict
from html import escape


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="ELTE Timetable",
    page_icon="📅",
    layout="wide"
)


# ============================================================
# CONSTANTS
# ============================================================

GROUPS = [
    "A",
    "B",
    "C",
    "D",
    "F",
    "G",
    "H",
    "J",
    "K",
    "L",
    "N",
    "P",
    "R",
    "S",
]


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>
    .app-subtitle {
        color: #666;
        font-size: 1.05rem;
        margin-top: -0.5rem;
        margin-bottom: 1.5rem;
    }

    .section-label {
        font-size: 0.95rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }

    .helper-text {
        color: #777;
        font-size: 0.88rem;
        margin-top: -0.4rem;
        margin-bottom: 0.8rem;
    }

    .result-summary {
        font-size: 0.95rem;
        color: #666;
        margin-bottom: 0.8rem;
    }

    .calendar-shell {
        overflow-x: auto;
        border: 1px solid #ddd;
        border-radius: 12px;
        background: #fff;
    }

    .calendar-grid {
        display: grid;
        grid-template-columns: 64px repeat(5, minmax(190px, 1fr));
        min-width: 1010px;
        position: relative;
    }

    .calendar-corner,
    .calendar-day-head {
        position: sticky;
        top: 0;
        z-index: 5;
        background: #f7f7f7;
        border-bottom: 1px solid #ddd;
    }

    .calendar-corner {
        left: 0;
        z-index: 7;
    }

    .calendar-day-head {
        text-align: center;
        font-weight: 700;
        padding: 10px 6px;
        border-left: 1px solid #ddd;
    }

    .calendar-day-head .date {
        display: block;
        font-size: 0.78rem;
        font-weight: 400;
        color: #777;
        margin-top: 2px;
    }

    .calendar-time-axis {
        position: relative;
        background: #fafafa;
        border-right: 1px solid #ddd;
    }

    .calendar-time-label {
        position: absolute;
        right: 7px;
        transform: translateY(-50%);
        color: #777;
        font-size: 0.72rem;
        white-space: nowrap;
    }

    .calendar-day {
        position: relative;
        border-left: 1px solid #ddd;
        background: #fff;
        overflow: hidden;
    }

    .calendar-gridline,
    .calendar-halfline {
        position: absolute;
        left: 0;
        right: 0;
        pointer-events: none;
    }

    .calendar-gridline {
        border-top: 1px solid #e3e3e3;
    }

    .calendar-halfline {
        border-top: 1px dashed #eee;
    }

    .calendar-event {
        position: absolute;
        box-sizing: border-box;
        overflow: hidden;
        border: 1px solid #bdbdbd;
        border-radius: 8px;
        padding: 6px 7px;
        background: #f4f4f4;
        color: #111;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }

    .calendar-event-time {
        font-size: 0.7rem;
        font-weight: 700;
        margin-bottom: 2px;
    }

    .calendar-event-title {
        font-size: 0.82rem;
        font-weight: 700;
        line-height: 1.15;
        margin-bottom: 3px;
    }

    .calendar-event-meta {
        font-size: 0.67rem;
        color: #555;
        line-height: 1.25;
    }

    .calendar-empty {
        color: #aaa;
        text-align: center;
        padding-top: 35px;
        font-size: 0.8rem;
    }

    @media (max-width: 700px) {
        .calendar-grid {
            min-width: 900px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(text):
    """Clean whitespace and simple HTML."""

    if not text:
        return ""

    text = text.replace("<br>", "\n")
    text = text.replace("<br/>", "\n")
    text = text.replace("<br />", "\n")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_line(line):
    """Normalize a pasted line."""

    if not line:
        return ""

    line = line.replace("\ufeff", "")
    line = line.replace("\xa0", " ")

    return re.sub(r"\s+", " ", line).strip()


# ============================================================
# GROUP PARSING
# ============================================================

def parse_group_line(line):
    """
    Parse a group line.

    Examples:

        A,B,C
        N,P,S
        G,K,R
        K
        A, C
        F,G,H

    Returns:
        ["A", "B", "C"]
    """

    if not line:
        return None

    line = normalize_line(line)

    # Remove possible bold markdown.
    line = line.replace("**", "")

    # Remove spaces.
    compact = line.replace(" ", "")

    # ALL is explicitly supported.
    if compact.upper() == "ALL":
        return ["ALL"]

    # Must consist only of group letters separated by commas.
    if not re.fullmatch(
        r"[A-Z](?:,[A-Z])*",
        compact
    ):
        # Use a safer direct pattern below.
        if not re.fullmatch(
            r"[A-Z](?:,[A-Z])*",
            compact
        ):
            return None

    groups = compact.split(",")

    # Every item must be an actual valid group.
    if not all(group in GROUPS for group in groups):
        return None

    return groups


def extract_groups_from_location(course_location):
    """
    Infer a group ONLY when the structured COURSE-LOCATION code
    ends with one of the known group letters.

    Examples:
        MENA-ESK -> K
        MAT1-MSK -> K
        KOZE-MSK -> K

    Not matches:
        KOZE-MEX
        MAR1-ELX
        MENA-ELY
        Marketing
        Katalin
    """

    if not course_location:
        return None

    code = normalize_line(str(course_location)).upper()

    # The entire value must be a COURSE-LOCATION style code.
    # This prevents ordinary text containing a group letter from matching.
    if not re.fullmatch(r"[A-Z0-9]+-[A-Z0-9]+", code):
        return None

    last_character = code[-1]

    if last_character in GROUPS:
        return [last_character]

    return None


# ============================================================
# DATE / TIME PARSING
# ============================================================

def parse_date_line(line):
    """
    Parse a flattened timetable date line.

    Example:

        2026.12.03 08:15-09:45 Marketing (BSc)

    Returns:
        date
        start_time
        end_time
        subject
    """

    line = normalize_line(line)

    pattern = (
        r"^"
        r"(\d{4}\.\d{2}\.\d{2})"
        r"\s+"
        r"(\d{1,2}:\d{2})"
        r"-"
        r"(\d{1,2}:\d{2})"
        r"\s+"
        r"(.+)"
        r"$"
    )

    match = re.match(pattern, line)

    if not match:
        return None

    date_text = match.group(1)
    start_time = match.group(2)
    end_time = match.group(3)
    subject = match.group(4).strip()

    try:
        date_obj = datetime.strptime(
            date_text,
            "%Y.%m.%d"
        ).date()
    except ValueError:
        return None

    return {
        "date": date_obj,
        "start_time": start_time,
        "end_time": end_time,
        "time": f"{start_time}-{end_time}",
        "subject": subject,
    }


# ============================================================
# COURSE / LESSON TYPE PARSING
# ============================================================

def parse_course_line(line):
    """
    Parse the line containing course codes and lesson type.

    Examples:

        GTI21AN108HU, GTI21AN108EN Lecture 12

        GTI21AN104HU előadás 11

        GTI21AN104HU szeminárium 8
    """

    line = normalize_line(line)

    # Find GTI course codes.
    course_codes = re.findall(
        r"\bGTI[A-Za-z0-9]+\b",
        line
    )

    # Remove course codes from the line.
    lesson_type = line

    for code in course_codes:
        lesson_type = lesson_type.replace(
            code,
            ""
        )

    # Remove commas left behind.
    lesson_type = lesson_type.replace(",", " ")

    lesson_type = re.sub(
        r"\s+",
        " ",
        lesson_type
    ).strip()

    return {
        "course_codes": course_codes,
        "lesson_type": lesson_type,
    }


# ============================================================
# LOCATION / ROOM / TEACHER PARSING
# ============================================================

def parse_location_line(line):
    """
    Parse:

        MAR1-ELX P201 Magyar Mária

    or:

        KOZE-MEX MT Zsolnai Alíz

    or:

        MENA-ELY Q101 Pádár Katalin

    or:

        MAR1-ELX R Aula Magyar Mária

    Structure:

        COURSE_LOCATION + ROOM + TEACHER
    """

    line = normalize_line(line)

    if not line:
        return {
            "course_location": "",
            "room": "",
            "teacher": "",
        }

    # --------------------------------------------------------
    # COURSE LOCATION
    # --------------------------------------------------------

    location_match = re.match(
        r"^([A-Za-z0-9]+-[A-Za-z0-9]+)\s+(.*)$",
        line
    )

    if not location_match:
        return {
            "course_location": "",
            "room": "",
            "teacher": line,
        }

    course_location = location_match.group(1)
    remaining = location_match.group(2).strip()

    # --------------------------------------------------------
    # ROOM
    # --------------------------------------------------------

    # Known room formats:
    #
    # MT
    # PP
    # P101
    # P201
    # Q101
    # R Aula
    #
    # We check "R Aula" first because it has two words.

    room_match = re.match(
        r"^(R\s+Aula|MT|PP|P\d+|Q\d+)\s+(.*)$",
        remaining
    )

    if room_match:

        room = room_match.group(1)
        teacher = room_match.group(2).strip()

    else:

        # Fallback:
        # first token is room, everything after is teacher.

        parts = remaining.split(maxsplit=1)

        if len(parts) == 1:
            room = parts[0]
            teacher = ""

        else:
            room = parts[0]
            teacher = parts[1]

    return {
        "course_location": course_location,
        "room": room,
        "teacher": teacher,
    }


# ============================================================
# FLATTENED TIMETABLE PARSER
# ============================================================

def parse_flattened_timetable(text):
    """
    Parse both ELTE flattened layouts.

    4-line:
        DATE
        COURSE
        GROUPS
        COURSE-LOCATION ROOM TEACHER

    3-line:
        DATE
        COURSE
        COURSE-LOCATION ROOM TEACHER

    For the 3-line form, the group is inferred ONLY from the final
    character of the structured COURSE-LOCATION code.
    """

    lessons = []

    if not text:
        return lessons

    lines = [
        normalize_line(line)
        for line in text.splitlines()
        if normalize_line(line)
    ]

    def is_course_line(line):
        return bool(re.search(r"\bGTI[A-Za-z0-9]+\b", line))

    def is_location_line(line):
        return bool(re.match(
            r"^[A-Za-z0-9]+-[A-Za-z0-9]+\s+.+$",
            line
        ))

    date_indices = [
        i for i, line in enumerate(lines)
        if parse_date_line(line) is not None
    ]

    for date_index in date_indices:
        parsed_date = parse_date_line(lines[date_index])
        if parsed_date is None:
            continue

        course_line = None
        group_line = None
        location_line = None

        # Current 4-line layout: DATE / COURSE / GROUPS / LOCATION
        if date_index + 3 < len(lines):
            candidate_course = lines[date_index + 1]
            candidate_groups = lines[date_index + 2]
            candidate_location = lines[date_index + 3]

            if (
                is_course_line(candidate_course)
                and parse_group_line(candidate_groups) is not None
                and is_location_line(candidate_location)
            ):
                course_line = candidate_course
                group_line = candidate_groups
                location_line = candidate_location

        # Current 3-line layout: DATE / COURSE / LOCATION
        if course_line is None and date_index + 2 < len(lines):
            candidate_course = lines[date_index + 1]
            candidate_location = lines[date_index + 2]

            if (
                is_course_line(candidate_course)
                and is_location_line(candidate_location)
            ):
                course_line = candidate_course
                location_line = candidate_location

        # Legacy/reversed layout: GROUPS / LOCATION / DATE / COURSE
        if course_line is None and date_index >= 2 and date_index + 1 < len(lines):
            candidate_groups = lines[date_index - 2]
            candidate_location = lines[date_index - 1]
            candidate_course = lines[date_index + 1]

            if (
                parse_group_line(candidate_groups) is not None
                and is_location_line(candidate_location)
                and is_course_line(candidate_course)
            ):
                group_line = candidate_groups
                location_line = candidate_location
                course_line = candidate_course

        if course_line is None or location_line is None:
            continue

        explicit_groups = (
            parse_group_line(group_line)
            if group_line is not None
            else None
        )

        location_data = parse_location_line(location_line)
        course_data = parse_course_line(course_line)
        course_location = location_data["course_location"]

        if explicit_groups:
            groups = explicit_groups
            group_source = "explicit"
        else:
            inferred_groups = extract_groups_from_location(course_location)
            if inferred_groups:
                groups = inferred_groups
                group_source = "location"
            else:
                groups = ["ALL"]
                group_source = "all"

        lessons.append({
            "date": parsed_date["date"],
            "start_time": parsed_date["start_time"],
            "end_time": parsed_date["end_time"],
            "time": parsed_date["time"],
            "subject": parsed_date["subject"],
            "course_codes": course_data["course_codes"],
            "lesson_type": course_data["lesson_type"],
            "groups": groups,
            "group_source": group_source,
            "course_location": course_location,
            "room": location_data["room"],
            "teacher": location_data["teacher"],
        })

    return lessons


# ============================================================
# MARKDOWN TABLE PARSER
# ============================================================

def parse_markdown_table(text):
    """
    Optional support for the original Markdown table format.

    Expected:

        | date | time | subject | lesson type | room | teacher |
        | ...  | ...  | ...     | ...          | ...  | ...     |
    """

    lessons = []

    if not text:
        return lessons

    for raw_line in text.splitlines():

        line = raw_line.strip()

        if not line.startswith("|"):
            continue

        # Ignore separator lines.
        if re.match(
            r"^\|\s*:?-+\s*\|",
            line
        ):
            continue

        cells = [
            cell.strip()
            for cell in line.split("|")
        ]

        # Remove empty edges.
        if cells and cells[0] == "":
            cells = cells[1:]

        if cells and cells[-1] == "":
            cells = cells[:-1]

        if len(cells) < 6:
            continue

        date_text = cells[0]
        time_text = cells[1]
        subject_cell = cells[2]
        lesson_cell = cells[3]
        room = cells[4]
        teacher = cells[5]

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        try:
            date_obj = datetime.strptime(
                date_text,
                "%Y.%m.%d"
            ).date()
        except ValueError:
            continue

        # ----------------------------------------------------
        # TIME
        # ----------------------------------------------------

        time_match = re.match(
            r"^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$",
            time_text
        )

        if not time_match:
            continue

        start_time = time_match.group(1)
        end_time = time_match.group(2)

        # ----------------------------------------------------
        # SUBJECT
        # ----------------------------------------------------

        subject_clean = (
            subject_cell
            .replace("<br>", "\n")
            .replace("<br/>", "\n")
            .replace("<br />", "\n")
        )

        subject_lines = [
            x.strip()
            for x in subject_clean.split("\n")
            if x.strip()
        ]

        course_codes = re.findall(
            r"\bGTI[A-Za-z0-9]+\b",
            subject_clean
        )

        subject = subject_lines[0] if subject_lines else ""

        # ----------------------------------------------------
        # EXPLICIT GROUP
        # ----------------------------------------------------

        explicit_groups = []

        group_matches = re.findall(
            r"\*\*\s*([A-Z](?:\s*,\s*[A-Z])*)\s*\*\*",
            lesson_cell
        )

        for match in group_matches:

            for group in re.findall(
                r"[A-Z]",
                match
            ):

                if (
                    group in GROUPS
                    and group not in explicit_groups
                ):
                    explicit_groups.append(group)

        # ----------------------------------------------------
        # COURSE LOCATION
        # ----------------------------------------------------

        course_location_matches = re.findall(
            r"\b[A-Za-z0-9]+-[A-Za-z0-9]+\b",
            lesson_cell
        )

        course_location = (
            course_location_matches[-1]
            if course_location_matches
            else ""
        )

        # ----------------------------------------------------
        # LESSON TYPE
        # ----------------------------------------------------

        lesson_type = lesson_cell

        lesson_type = re.sub(
            r"\*\*\s*[A-Z](?:\s*,\s*[A-Z])*\s*\*\*",
            "",
            lesson_type
        )

        if course_location:
            lesson_type = lesson_type.replace(
                course_location,
                ""
            )

        lesson_type = lesson_type.replace(
            "<br>",
            " "
        )

        lesson_type = re.sub(
            r"\s+",
            " ",
            lesson_type
        ).strip()

        # ----------------------------------------------------
        # GROUP LOGIC
        # ----------------------------------------------------

        if explicit_groups:

            groups = explicit_groups
            group_source = "explicit"

        else:

            inferred_groups = extract_groups_from_location(
                course_location
            )

            if inferred_groups:

                groups = inferred_groups
                group_source = "location"

            else:

                groups = ["ALL"]
                group_source = "all"

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        lessons.append(
            {
                "date": date_obj,
                "start_time": start_time,
                "end_time": end_time,
                "time": f"{start_time}-{end_time}",
                "subject": subject,
                "course_codes": course_codes,
                "lesson_type": lesson_type,
                "groups": groups,
                "group_source": group_source,
                "course_location": course_location,
                "room": room,
                "teacher": teacher,
            }
        )

    return lessons


# ============================================================
# AUTOMATIC FORMAT DETECTION
# ============================================================

def parse_timetable(text):
    """
    Automatically determine whether the input is:

        1. Flattened timetable
        2. Markdown table
    """

    if not text or not text.strip():
        return []

    # If there are Markdown table pipes, use Markdown parser.
    if "|" in text:

        markdown_lessons = parse_markdown_table(
            text
        )

        if markdown_lessons:
            return markdown_lessons

    # Otherwise use the flattened format.
    return parse_flattened_timetable(
        text
    )


# ============================================================
# FILTER
# ============================================================

def filter_lessons(lessons, selected_group):
    """
    Filter lessons by the explicit group first, then by COURSE-LOCATION.

    Rules:
    1. If the lesson has an explicit group line, ONLY that explicit group
       assignment is used. COURSE-LOCATION X/Y is ignored in this case.
       Example: explicit "A, C" -> visible for A and C, not K.

    2. If there is NO explicit group line, inspect the final character of
       the structured COURSE-LOCATION code:
         ...-K -> K only
         ...-L -> L only
         ...-X -> every selected group
         ...-Y -> every selected group

    3. Never search arbitrary lesson text for a group letter.
    """

    selected_group = str(selected_group).strip().upper()

    if selected_group == "ALL":
        return lessons

    if selected_group not in GROUPS:
        return []

    result = []

    for lesson in lessons:
        group_source = str(lesson.get("group_source", "")).strip().lower()

        # ------------------------------------------------------------
        # Rule 1: explicit group assignment is authoritative.
        # X/Y must NOT make an explicitly grouped lesson universal.
        # ------------------------------------------------------------
        if group_source == "explicit":
            groups = {
                str(group).strip().upper()
                for group in lesson.get("groups", [])
            }
            if selected_group in groups:
                result.append(lesson)
            continue

        # ------------------------------------------------------------
        # Rule 2: no explicit group -> use the structured location suffix.
        # ------------------------------------------------------------
        course_location = normalize_line(
            str(lesson.get("course_location", ""))
        ).upper()

        if re.fullmatch(r"[A-Z0-9]+-[A-Z0-9]+", course_location):
            suffix = course_location[-1]

            # Specific group suffix: ...-K, ...-L, etc.
            if suffix == selected_group:
                result.append(lesson)
                continue

            # X/Y mean no specific student group, so show for every
            # selected group -- but ONLY because there was no explicit
            # group assignment.
            if suffix in {"X", "Y"}:
                result.append(lesson)

    return result


# ============================================================
# SORT
# ============================================================

def sort_lessons(lessons):

    return sorted(
        lessons,
        key=lambda lesson: (
            lesson["date"],
            time_to_minutes(
                lesson["start_time"]
            )
        )
    )


def time_to_minutes(time_string):

    hour, minute = map(
        int,
        time_string.split(":")
    )

    return hour * 60 + minute


# ============================================================
# DISPLAY HELPERS
# ============================================================

def format_day(date_obj):

    days = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    return (
        f"{days[date_obj.weekday()]}, "
        f"{date_obj.strftime('%d.%m.')}"
    )


def render_lesson_card(lesson):

    subject = escape(
        str(lesson["subject"])
    )

    lesson_type = escape(
        str(lesson["lesson_type"])
    )

    room = escape(
        str(lesson["room"])
    )

    teacher = escape(
        str(lesson["teacher"])
    )

    course_location = escape(
        str(lesson["course_location"])
    )

    st.markdown(
        f"""
        <div class="lesson-card">

            <div class="lesson-time">
                {lesson["time"]}
            </div>

            <div class="lesson-subject">
                {subject}
            </div>

            <div class="lesson-type">
                {lesson_type}
            </div>

            <div class="lesson-info">
                <b>Room:</b> {room}<br>
                <b>Teacher:</b> {teacher}<br>
                <b>Course:</b> {course_location}
            </div>

        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# CALENDAR
# ============================================================


def render_week(lessons, week_start):
    days = [week_start + timedelta(days=i) for i in range(5)]

    lessons_by_date = defaultdict(list)
    for lesson in lessons:
        if week_start <= lesson["date"] <= week_start + timedelta(days=4):
            lessons_by_date[lesson["date"]].append(lesson)

    all_week_lessons = [
        lesson
        for day in days
        for lesson in lessons_by_date.get(day, [])
    ]

    if not all_week_lessons:
        return

    def mins(value):
        return time_to_minutes(value)

    earliest = min(mins(x["start_time"]) for x in all_week_lessons)
    latest = max(mins(x["end_time"]) for x in all_week_lessons)

    grid_start = max(0, (earliest // 30) * 30 - 30)
    grid_end = min(24 * 60, ((latest + 29) // 30) * 30 + 30)

    px_per_minute = 1.25
    grid_height = max(700, int((grid_end - grid_start) * px_per_minute))

    html = [
        '<div class="calendar-shell">',
        '<div class="calendar-grid">',
        '<div class="calendar-corner"></div>',
    ]

    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    for day, name in zip(days, names):
        html.append(
            f'<div class="calendar-day-head">{escape(name)}'
            f'<span class="date">{day.strftime("%d.%m.%Y")}</span></div>'
        )

    html.append(
        f'<div class="calendar-time-axis" style="height:{grid_height}px;">'
    )

    for minute in range(grid_start, grid_end + 1, 60):
        top = (minute - grid_start) * px_per_minute
        html.append(
            f'<div class="calendar-time-label" style="top:{top:.1f}px;">'
            f'{minute // 60:02d}:00</div>'
        )

    html.append("</div>")

    def grid_lines():
        result = []
        for minute in range(grid_start, grid_end + 1, 30):
            top = (minute - grid_start) * px_per_minute
            cls = "calendar-gridline" if minute % 60 == 0 else "calendar-halfline"
            result.append(f'<div class="{cls}" style="top:{top:.1f}px;"></div>')
        return "".join(result)

    def layout(day_lessons):
        events = []
        for lesson in sorted(
            day_lessons,
            key=lambda x: (mins(x["start_time"]), mins(x["end_time"]))
        ):
            events.append({
                "lesson": lesson,
                "start": mins(lesson["start_time"]),
                "end": max(mins(lesson["end_time"]), mins(lesson["start_time"]) + 15),
                "column": 0,
            })

        # Assign columns for overlapping events.
        columns = []
        for event in events:
            placed = False
            for column_index, column_events in enumerate(columns):
                if all(
                    event["start"] >= other["end"]
                    or event["end"] <= other["start"]
                    for other in column_events
                ):
                    column_events.append(event)
                    event["column"] = column_index
                    placed = True
                    break
            if not placed:
                event["column"] = len(columns)
                columns.append([event])

        # Calculate overlap width separately for each event.
        for event in events:
            overlapping = [
                other for other in events
                if event["start"] < other["end"]
                and event["end"] > other["start"]
            ]
            event["total_columns"] = max(
                1,
                max(other["column"] for other in overlapping) + 1
            )

        return events

    for day in days:
        day_lessons = lessons_by_date.get(day, [])

        html.append(
            f'<div class="calendar-day" style="height:{grid_height}px;">'
        )
        html.append(grid_lines())

        if not day_lessons:
            html.append('<div class="calendar-empty">No lessons</div>')

        for event in layout(day_lessons):
            lesson = event["lesson"]
            top = (event["start"] - grid_start) * px_per_minute
            height = max(
                32,
                (event["end"] - event["start"]) * px_per_minute
            )

            total = event["total_columns"]
            width = 100 / total
            left = event["column"] * width

            subject = escape(str(lesson.get("subject", "")))
            lesson_type = escape(str(lesson.get("lesson_type", "")))
            room = escape(str(lesson.get("room", "")))
            teacher = escape(str(lesson.get("teacher", "")))
            course = escape(str(lesson.get("course_location", "")))
            groups = escape(", ".join(lesson.get("groups", [])))

            html.append(
                f'''
                <div class="calendar-event"
                     style="top:{top:.1f}px;height:{height:.1f}px;"
                     data-column="{event["column"]}">
                    <div class="calendar-event-time">{escape(lesson["time"])}</div>
                    <div class="calendar-event-title">{subject}</div>
                    <div class="calendar-event-meta">
                        {lesson_type}<br>
                        {room} · {teacher}<br>
                        {course} · {groups}
                    </div>
                </div>
                '''
            )

        # Add CSS variables so each event's column is positioned correctly.
        # We do this after building the event HTML to keep the markup simple.
        # The column attribute is converted to inline position here.
        # Replace each event's data-column with actual positioning.
        current = html[-1] if html else ""
        if current:
            pass

        html.append("</div>")

    html.append("</div></div>")

    # Add horizontal positioning to every event using its data-column and
    # total column count. The event markup above is rebuilt below with the
    # correct inline left/width values.
    raw = "".join(html)

    def fix_event(match):
        attrs = match.group(1)
        column = int(match.group(2))
        total = int(match.group(3))
        width = 100 / total
        left = column * width
        return (
            '<div class="calendar-event"'
            + attrs
            + f' style="top:{match.group(4)};height:{match.group(5)};'
            + f'left:calc({left:.4f}% + 2px);'
            + f'width:calc({width:.4f}% - 4px);">'
        )

    # The generated markup already has the vertical values. Injecting
    # horizontal placement is easier by rebuilding event tags with regex.
    pattern = (
        r'<div class="calendar-event"'
        r'([^>]*)'
        r' style="top:([^;]+);height:([^;]+);"'
        r' data-column="(\d+)">'
    )

    # Because total_columns is not stored in the tag, rebuild the day
    # rendering once more in a compact and deterministic way.
    # Remove the temporary event markup and render it directly instead.
    html = [
        '<div class="calendar-shell"><div class="calendar-grid">',
        '<div class="calendar-corner"></div>',
    ]

    for day, name in zip(days, names):
        html.append(
            f'<div class="calendar-day-head">{escape(name)}'
            f'<span class="date">{day.strftime("%d.%m.%Y")}</span></div>'
        )

    html.append(
        f'<div class="calendar-time-axis" style="height:{grid_height}px;">'
    )
    for minute in range(grid_start, grid_end + 1, 60):
        top = (minute - grid_start) * px_per_minute
        html.append(
            f'<div class="calendar-time-label" style="top:{top:.1f}px;">'
            f'{minute // 60:02d}:00</div>'
        )
    html.append("</div>")

    for day in days:
        day_lessons = lessons_by_date.get(day, [])
        html.append(
            f'<div class="calendar-day" style="height:{grid_height}px;">'
        )
        html.append(grid_lines())

        if not day_lessons:
            html.append('<div class="calendar-empty">No lessons</div>')

        for event in layout(day_lessons):
            lesson = event["lesson"]
            top = (event["start"] - grid_start) * px_per_minute
            height = max(32, (event["end"] - event["start"]) * px_per_minute)
            total = event["total_columns"]
            width = 100 / total
            left = event["column"] * width

            subject = escape(str(lesson.get("subject", "")))
            lesson_type = escape(str(lesson.get("lesson_type", "")))
            room = escape(str(lesson.get("room", "")))
            teacher = escape(str(lesson.get("teacher", "")))
            course = escape(str(lesson.get("course_location", "")))
            groups = escape(", ".join(lesson.get("groups", [])))

            html.append(
                f'<div class="calendar-event" '
                f'style="top:{top:.1f}px;height:{height:.1f}px;'
                f'left:calc({left:.4f}% + 2px);'
                f'width:calc({width:.4f}% - 4px);">'
                f'<div class="calendar-event-time">{escape(lesson["time"])}</div>'
                f'<div class="calendar-event-title">{subject}</div>'
                f'<div class="calendar-event-meta">'
                f'{lesson_type}<br>{room} · {teacher}<br>{course} · {groups}'
                f'</div></div>'
            )

        html.append("</div>")

    html.append("</div></div>")

    st.markdown("".join(html), unsafe_allow_html=True)


# ============================================================
# USER INTERFACE
# ============================================================

st.title("📅 ELTE Timetable")
st.markdown(
    '<div class="app-subtitle">Turn your ELTE timetable data into a simple weekly calendar.</div>',
    unsafe_allow_html=True,
)

# Keep the essential choice in the main page rather than hiding it in a sidebar.
st.markdown('<div class="section-label">Your group</div>', unsafe_allow_html=True)
selected_group = st.selectbox(
    "Your group",
    GROUPS,
    index=GROUPS.index("K") if "K" in GROUPS else 0,
    label_visibility="collapsed",
)

st.markdown('<div class="section-label">Paste your ELTE timetable data</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="helper-text">Copy your timetable data from ELTE and paste it below.</div>',
    unsafe_allow_html=True,
)

markdown_text = st.text_area(
    "Timetable data",
    height=300,
    placeholder="Paste your ELTE timetable here...",
    label_visibility="collapsed",
)

generate = st.button(
    "Generate timetable",
    type="primary",
    use_container_width=True,
)

# Keep the pasted data in session state so the generated calendar remains
# visible when the user changes the group or navigates between weeks.
if "timetable_text" not in st.session_state:
    st.session_state.timetable_text = ""

if generate:
    st.session_state.timetable_text = markdown_text

if st.session_state.timetable_text.strip():
    all_lessons = sort_lessons(
        parse_timetable(st.session_state.timetable_text)
    )
    filtered_lessons = sort_lessons(
        filter_lessons(all_lessons, selected_group)
    )

    st.divider()

    if not all_lessons:
        st.error(
            "I couldn't find any lessons in that data. "
            "Please check that you copied the timetable data from ELTE correctly."
        )
    elif not filtered_lessons:
        st.warning(
            f"No lessons were found for group {selected_group}. "
            "Try another group or check the pasted timetable data."
        )
    else:
        st.subheader("Your timetable")

        first_date = min(lesson["date"] for lesson in filtered_lessons)
        last_date = max(lesson["date"] for lesson in filtered_lessons)

        first_week = first_date - timedelta(days=first_date.weekday())
        last_week = last_date - timedelta(days=last_date.weekday())

        if "calendar_week" not in st.session_state:
            st.session_state.calendar_week = first_week

        # Keep the selected week inside the available timetable range.
        if st.session_state.calendar_week < first_week:
            st.session_state.calendar_week = first_week
        if st.session_state.calendar_week > last_week:
            st.session_state.calendar_week = last_week

        current_week = st.session_state.calendar_week

        nav1, nav2, nav3 = st.columns([1, 2, 1])

        with nav1:
            if st.button(
                "← Previous week",
                use_container_width=True,
                disabled=current_week <= first_week,
            ):
                st.session_state.calendar_week = current_week - timedelta(days=7)
                st.rerun()

        with nav2:
            st.markdown(
                f"<div style='text-align:center;font-weight:700;padding:7px 0;'>"
                f"{current_week.strftime('%d.%m.')} – "
                f"{(current_week + timedelta(days=4)).strftime('%d.%m.%Y')}"
                f"</div>",
                unsafe_allow_html=True,
            )

        with nav3:
            if st.button(
                "Next week →",
                use_container_width=True,
                disabled=current_week >= last_week,
            ):
                st.session_state.calendar_week = current_week + timedelta(days=7)
                st.rerun()

        week_lessons = [
            lesson
            for lesson in filtered_lessons
            if current_week <= lesson["date"] <= current_week + timedelta(days=4)
        ]

        st.markdown(
            f'<div class="result-summary">'
            f'{len(filtered_lessons)} lessons · Group {escape(selected_group)}'
            f'</div>',
            unsafe_allow_html=True,
        )

        if week_lessons:
            render_week(filtered_lessons, current_week)
        else:
            st.info("No lessons this week.")

        with st.expander("How do I get my timetable data?"):
            st.markdown(
                "Open your ELTE timetable, copy the timetable data, and paste it "
                "into the box above. You do not need to edit or format the text."
            )

else:
    with st.expander("How do I get my timetable data?"):
        st.markdown(
            "Open your ELTE timetable, copy the timetable data, and paste it "
            "into the box above. You do not need to edit or format the text."
        )

    st.info("Paste your timetable data above, then click **Generate timetable**.")

