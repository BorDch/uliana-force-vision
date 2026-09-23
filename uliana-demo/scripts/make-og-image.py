"""Render the static social preview image for the ULIANA landing page.

The 1200 x 630 PNG in `public/` is a committed asset; this script only exists so
the image can be regenerated deterministically. It is a development tool and is
not part of the site build.

Usage: python3 scripts/make-og-image.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT / "public" / "og-image.png"

WIDTH, HEIGHT = 1200, 630
BACKGROUND = (246, 240, 232)
INK = (41, 43, 41)
MUTED = (87, 83, 78)
ACCENT = (173, 87, 63)
ACCENT_DARK = (143, 74, 56)
ZONE = (216, 185, 167)

SERIF_BOLD = "/usr/share/fonts/liberation/LiberationSerif-Bold.ttf"
SERIF_REGULAR = "/usr/share/fonts/liberation/LiberationSerif-Regular.ttf"
SANS_BOLD = "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
SANS_REGULAR = "/usr/share/fonts/TTF/DejaVuSans.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def draw_rig(draw: ImageDraw.ImageDraw, left: int, top: int, scale: float) -> None:
    """Small side-view push-up rig plus the two hand-zone channels.

    All geometry is expressed in fractions of `scale` so the sketch scales.
    """
    def point(x: float, y: float) -> tuple[float, float]:
        return left + x * scale, top + y * scale

    def stroke(width: float) -> int:
        return max(2, round(width * scale))

    # Mat
    draw.line([point(0.02, 0.86), point(0.58, 0.86)], fill=(196, 181, 166), width=stroke(0.012))
    shoulder = point(0.2, 0.5)
    ankle = point(0.55, 0.82)
    hip = point(0.34, 0.63)
    knee = point(0.46, 0.74)
    wrist = point(0.13, 0.82)

    # Bent arm: wrist to elbow to shoulder.
    elbow = ((wrist[0] + shoulder[0]) / 2 - 0.08 * scale, (wrist[1] + shoulder[1]) / 2 - 0.02 * scale)
    draw.line([wrist, elbow, shoulder], fill=INK, width=stroke(0.03), joint="curve")
    draw.line([shoulder, ankle], fill=INK, width=stroke(0.035))
    draw.line([hip, knee], fill=(150, 140, 130), width=stroke(0.018))

    head_radius = 0.062 * scale
    head = (shoulder[0] - 0.068 * scale, shoulder[1] - 0.062 * scale)
    draw.ellipse(
        [head[0] - head_radius, head[1] - head_radius, head[0] + head_radius, head[1] + head_radius],
        fill=ACCENT,
    )

    joint_radius = 0.017 * scale
    for joint in (hip, knee):
        draw.ellipse(
            [joint[0] - joint_radius, joint[1] - joint_radius, joint[0] + joint_radius, joint[1] + joint_radius],
            fill=(255, 250, 242),
            outline=ACCENT,
            width=stroke(0.006),
        )

    # Hand zones with the relative pulse rings.
    for index, x in enumerate((0.72, 0.9)):
        centre = point(x, 0.5)
        radius_x, radius_y = ((0.15, 0.1) if index == 0 else (0.125, 0.078))
        draw.ellipse(
            [centre[0] - radius_x * scale, centre[1] - radius_y * scale,
             centre[0] + radius_x * scale, centre[1] + radius_y * scale],
            fill=ZONE,
        )
        ring_x, ring_y = radius_x + 0.02, radius_y + 0.02
        draw.ellipse(
            [centre[0] - ring_x * scale, centre[1] - ring_y * scale,
             centre[0] + ring_x * scale, centre[1] + ring_y * scale],
            outline=ACCENT,
            width=stroke(0.01),
        )
        bar_y = centre[1] + radius_y * scale + 0.05 * scale
        draw.line([centre[0] - 0.135 * scale, bar_y, centre[0] + 0.135 * scale, bar_y], fill=(196, 181, 166), width=stroke(0.012))
        draw.line([centre[0] - 0.135 * scale, bar_y, centre[0] + 0.01 * scale, bar_y], fill=ACCENT, width=stroke(0.012))


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    # Soft accent wash on the right half.
    wash = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    wash_draw = ImageDraw.Draw(wash)
    wash_draw.ellipse([720, -120, 1320, 480], fill=(218, 189, 164, 70))
    image = Image.alpha_composite(image.convert("RGBA"), wash).convert("RGB")
    draw = ImageDraw.Draw(image)

    draw.rectangle([0, 0, 10, HEIGHT], fill=ACCENT)

    draw.text((64, 62), "SKOLTECH HACK10 · INNOVATION WORKSHOP 2026", font=font(SANS_BOLD, 19), fill=ACCENT_DARK)
    draw.text((64, 116), "ULIANA", font=font(SERIF_BOLD, 40), fill=INK)
    draw.line([64, 178, 604, 178], fill=(216, 204, 192), width=2)

    draw.text((64, 208), "A recorded push-up set,", font=font(SERIF_BOLD, 66), fill=INK)
    draw.text((64, 286), "read rep by rep.", font=font(SERIF_BOLD, 66), fill=INK)

    body = [
        "Pose tracking plus two hand-zone signal channels,",
        "assembled after the session. Rep count, tempo, range",
        "and a relative left / right pattern — per repetition.",
    ]
    for index, line in enumerate(body):
        draw.text((64, 396 + index * 30), line, font=font(SANS_REGULAR, 21), fill=MUTED)

    draw.text(
        (64, 552),
        "Working prototype · illustrative data · not live coaching, not a medical assessment",
        font=font(SANS_BOLD, 17),
        fill=(107, 100, 93),
    )

    draw_rig(draw, left=740, top=150, scale=330)

    image.save(DESTINATION, "PNG", optimize=True)
    print(f"wrote {DESTINATION} ({DESTINATION.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
