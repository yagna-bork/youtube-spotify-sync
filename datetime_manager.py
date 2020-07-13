from datetime import datetime, timezone
from tzlocal import get_localzone
import pytz
import time


def get_time_now():
    return datetime.utcnow()


def gmt_to_local_timezone(gmt_dt):
    return gmt_dt.replace(tzinfo=timezone.gmt).astimezone(tz=None)


# converts a string representation of yt datetime (which is in utc)
# and converts it to datetime with local timezone
def parse_youtube_datetime(yt_datetime):
    return datetime.strptime(yt_datetime, "%Y-%m-%dT%H:%M:%SZ")


# timestamps must be floats
def timestamp_str_to_datetime(timestamp):
    return datetime.fromtimestamp(float(timestamp))


def datetime_to_timestamp_str(dt):
    return datetime.timestamp(dt)


def generate_times_stamps():
    for i in range(3):
        now = get_time_now()
        now_ts = datetime.timestamp(now)
        print(now_ts)
        time.sleep(3)


if __name__ == '__main__':
    print(timestamp_str_to_datetime("1594656018.86631"))
