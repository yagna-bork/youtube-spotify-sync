import ast


# TODO handle FindFail gracefully in calling program
# TODO Cancel on ctrl+c press
# TODO display AR-like text of current thing its doing
WHEEL_STEPS = 10
MAX_WAIT_DURATION = 0.5


# parse string "[('example', 1), ('example2', 2)]" into ["example", "example2", "example2"]
def parse_instrutions_from_args():
    args = sys.argv[1:]
    condensed_instructions = ast.literal_eval(args[0])
    instructions = []
    for playlist_name, num_songs in condensed_instructions:
        instructions.extend([playlist_name] * num_songs)
    return instructions


def apply_setting():
    Settings.MoveMouseDelay = 0
    Settings.ActionLogs = False


def find_all_lines():
    line_pattern = Pattern("song_divider.png").exact()
    line_matches = list(findAll(line_pattern))
    line_matches.sort(key=lambda m: m.getTarget().getY())
    return line_matches


# click a match if found and return weather it was clicked or not
def click_if_found(match, duration=MAX_WAIT_DURATION):
    try:
        wait(match, duration)
    except:
        return False
    else:
        click(match)
        return True


def wait_and_do(duration, func):
    wait(duration)
    return func() 


def run():
    instructions = parse_instrutions_from_args()
    num_songs = len(instructions)
    apply_setting()
    openApp("Spotify")

    # open local files
    doubleClick(wait("radio_icon.png", 1))
    wait_and_do(0.7, lambda: type(Key.DOWN*6))

    # scroll to bottom of page
    scroll_anchor = exists("title_text.png", 1)
    x, y = scroll_anchor.getBottomLeft().getX(), scroll_anchor.getBottomLeft().getY()
    width = 200
    region_around_anchor = Region(x, y, width, width)
    max_scrolling = 50
    for i in range(max_scrolling):
        old_region_around_anchor = capture(region_around_anchor)
        wheel(scroll_anchor, Button.WHEEL_UP, WHEEL_STEPS)
        # if region doesnt change then scroll down did nothing, which means bottom reached
        if region_around_anchor.has(old_region_around_anchor, 0):
            break
        if i == max_scrolling - 1:
            exit(130)  # exited without getting to bottom of local files for some reason

    # click in empty region right of all lines to clear selection
    bottom_line = find_all_lines()[-1]
    click(bottom_line.getTopRight().offset(10, 0))

    # TODO quicker way to do this, use y-distance between TITLE and first line then wheel?
    lines = find_all_lines()
    bottom_line = lines[-1]
    bottom_song = bottom_line.getCenter().offset(0, -10)
    click(bottom_song)
    mouseMove(bottom_line.getTopRight().offset(10, 0))
    type(Key.UP*(num_songs-1))  # highlights to top song to add

    # TODO fail gracefully here, indicate which songs were succesfully added
    for target_playlist in instructions:
        options_btn = wait("more_dots.png", MAX_WAIT_DURATION); click(options_btn)
        add_to_playlist_btn = wait("add_to_playlist_img.png", MAX_WAIT_DURATION); click(add_to_playlist_btn)
        mouseMove(-150, 5)
        wait_and_do(0.1, lambda: paste(unicode(target_playlist, "utf-8")))
        curr_x, target_y = Env.getMouseLocation().getX(), add_to_playlist_btn.getTarget().getY()
        playlist_to_add = wait_and_do(0.1, lambda: Location(curr_x, target_y))
        wait_and_do(0.2, lambda: click(playlist_to_add))
        if click_if_found("skip_duplicate_img.png", duration=0.5):
            wait_and_do(0.3, lambda: click(options_btn.offset(-30, 0)))

        # clear any selection because mouse is hovering over previous song
        end_of_bottom_line = find_all_lines()[-1].getTopRight()
        target_x, curr_y = end_of_bottom_line.getX()+25, Env.getMouseLocation().getY()
        mouseMove(Location(target_x, curr_y))

        type(Key.DOWN)


run()
