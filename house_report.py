#!/usr/bin/env python3
import argparse
import base64
import cmd
import dataclasses
import datetime
import io
import pathlib
import os
import re
import sys
import subprocess

from PIL import Image, ImageOps, ExifTags



@dataclasses.dataclass
class ReportData:
    effective_date: str
    property_address: str
    author: str
    photo_list: list


def render_report_data(report_data):
    date_format ="%B %-d, %Y"
    formatted_date = report_data.effective_date.strftime(date_format)

    lines = [
        f"% Home Owner's Report for {report_data.property_address}",
        f"% {report_data.author}",
        f"% {formatted_date}"
    ]

    for i, (photo_path, image, comment) in enumerate(report_data.photo_list):
        # Convert each image into an equivalent data url
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        img_str = base64.b64encode(buffer.getvalue()).decode()
        embedded_img = f"data:image/jpeg;base64,{img_str}"

        # Add the comment as a header, the image, then a newline
        lines.append(f"#### {i + 1}. {comment}")
        lines.append(f"![]({embedded_img}){{width=90%}}")
        lines.append("\n")

    return "\n".join(lines)


def markdown_to_html(markdown_input):
    args = [
        'pandoc',
        '--table-of-contents',
        '--toc-depth=6',
        '--from=markdown',
        '--to=html5',
        '--include-in-header=style.css',
    ]
    html_output = subprocess.check_output(args, input=markdown_input, universal_newlines=True)
    return html_output


def shrink_image(image):
    # 900 px is "ideal" because it displays at 100% by default on a standard HD
    # monitor.
    ideal_max_dimension = 900
    img_w, img_h = image.size
    max_dim = max(img_w, img_h)
    scale = max_dim / ideal_max_dimension
    scaled_w, scaled_h = int(img_w / scale), int(img_h / scale)
    sm_image = image.resize((scaled_w, scaled_h), Image.BICUBIC)
    sm_image = ImageOps.exif_transpose(sm_image)
    return sm_image


def get_most_recent_photos(photo_dir):
    attachable_files = photo_dir.iterdir()

    tag_id = 40092
    for photo_path in attachable_files:
        image = Image.open(photo_path)
        image = shrink_image(image)
        exifdata = image.getexif()

        comment = exifdata.get(tag_id, b"")
        if isinstance(comment, bytes):
            comment = comment.decode().replace("\0", "")
            if not comment:
                continue
        yield photo_path, image, comment


class BashCompleteArgParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _bash_complete_recursor(self, matches=None):
        if os.environ.get("COMP_LINE") and os.environ.get("COMP_POINT"):
            command, curr_word, prev_word = sys.argv[1:]
            comp_line = os.environ.get("COMP_LINE")

        matches = set()
        for action in self._actions:
            for opt_string in action.option_strings:
                if opt_string.startswith(curr_word):
                    matches.add(opt_string)
        return matches


    def parse_args(self):
        if os.environ.get("COMP_LINE") and os.environ.get("COMP_POINT"):
            matches = self._bash_complete_recursor()
            if matches:
                print("\n".join(matches))
            quit()
        return super().parse_args()


def get_arg_parser():
    description = """This program generates a markdown-formatted report of
    issues you find in your home. It is expected that the photos taken are
    .jpeg-formatted and have comments added via metadata.
    """
    parser = BashCompleteArgParser(description=description)
    parser.add_argument(
        "--author",
        type=str,
        help="The name of the person preparing the report. Likely you."
    )
    parser.add_argument(
        "--property-address",
        type=str,
        help="Address of the property."
    )
    parser.add_argument(
        "--photo-path",
        type=pathlib.Path,
        help=(
            "A path to a directory containing .jpg photos. It is assumed "
            "comments have been added to their metadata."
        )
    )
    return parser


def main():
    parser = get_arg_parser()
    args = parser.parse_args()
    most_recent_photos = tuple(get_most_recent_photos(args.photo_path))

    report_data = ReportData(
        datetime.datetime.today(),
        args.property_address,
        args.author,
        most_recent_photos
    )

    report_filepath = pathlib.Path() / "report.md"
    markdown_input = render_report_data(report_data)

    with report_filepath.open("w") as f:
        print(markdown_input, file=f)
    with report_filepath.with_suffix(".html").open("w") as f:
        print(markdown_to_html(markdown_input), file=f)

if __name__ == "__main__":
    main()

