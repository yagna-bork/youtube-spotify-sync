import csv


def get_inputs():
    inputs = {}
    with open('input.csv') as file:
        reader = csv.reader(file)
        for idx, row in enumerate(reader):
            playlist_id, download_str = row[0], row[1]

            if playlist_id[0] == "!":
                continue

            if download_str == 'true':
                inputs[playlist_id] = True
            elif download_str == 'false':
                inputs[playlist_id] = False
            else:
                inputs[playlist_id] = None
    return inputs


if __name__ == '__main__':
    print(get_inputs())
