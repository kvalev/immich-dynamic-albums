from argparse import ArgumentParser, ArgumentTypeError
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Union

import itertools
import json
import os
import time
import uuid

import jsonschema
import requests
import schedule

from semver.version import Version


class Immich:
    def __init__(self, immich_url: str, api_key: str) -> None:
        self.immich_url = immich_url.rstrip("/")
        self.api_key = api_key

    def whoami(self):
        return self._get("/api/users/me")

    def version(self):
        return self._get("/api/server/version")

    def get_people(self):
        return self._get("/api/people?size=1000&withHidden=false")

    def get_tags(self):
        return self._get("/api/tags")

    def get_albums(self):
        return self._get("/api/albums")

    def get_album(self, album_id: str, with_assets: bool = False):
        return self._get(f"/api/albums/{album_id}?withoutAssets={json.dumps(not with_assets)}")

    def create_album(self, name: str, description: str = None):
        # me = self.whoami()

        album_params = {
            "albumName": name,
            # "albumUsers": [{
            #     "userId": me["id"],
            #     "role": "editor",
            # }]
        }

        if description:
            album_params["description"] = description

        return self._post("/api/albums", album_params)

    def delete_assets_from_album(self, album_id: str, assets_ids: List[str]):
        delete_params = {"ids": assets_ids}

        return self._delete(f"/api/albums/{album_id}/assets", delete_params)

    def add_assets_to_album(self, album_id: str, assets_ids: List[str]):
        add_params = {"ids": assets_ids}

        return self._put(f"/api/albums/{album_id}/assets", add_params)

    def search(
        self,
        country: str = None,
        state: str = None,
        city: str = None,
        before: datetime = None,
        after: datetime = None,
        favorite: bool = None,
        person_ids: List[str] = None,
        tag_ids: List[str] = None,
    ):
        search_params = {
            "isVisible": True,
            "withExif": True,
        }

        if country:
            search_params["country"] = country
        if state:
            search_params["state"] = state
        if city:
            search_params["city"] = city
        if before:
            search_params["takenBefore"] = before.isoformat() # 2025-01-31T23:59:59.999Z
        if after:
            search_params["takenAfter"] = after.isoformat() # 2025-01-31T23:59:59.999Z
        if favorite is not None:
            search_params["isFavorite"] = favorite
        if person_ids:
            search_params["personIds"] = person_ids
        if tag_ids:
            search_params["tagIds"] = tag_ids

        return self._post("/api/search/metadata", search_params)

    def _get(self, path, payload = {}):
        return self._api("GET", path, payload)

    def _put(self, path, payload):
        return self._api("PUT", path, json.dumps(payload))

    def _post(self, path, payload):
        return self._api("POST", path, json.dumps(payload))

    def _delete(self, path, payload):
        return self._api("DELETE", path, json.dumps(payload))

    def _api(self, verb: str, path: str, payload: Any):
        url = f"{self.immich_url}/{path.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": self.api_key,
        }

        response = requests.request(verb, url, headers=headers, data=payload, timeout=60)
        if response.status_code >= 400:
            print(url)
            print(response.text)

        response.raise_for_status()

        return response.json()


def create_album_if_not_exists(immich: Immich, album_name: str) -> str:
    albums = immich.get_albums()
    album_names = {album["albumName"]: album for album in albums}

    if album_name in album_names.keys():
        return album_names[album_name]

    album = immich.create_album(album_name)

    return album


def read_json(config_path: Union[Path, str]) -> Any:
    with open(config_path) as f:
        return json.load(f)


def config_query_to_search_queries(query: Dict, people_mapping: Dict[str, str], tag_mapping: Dict[str, str]) -> List[Dict]:
    if "people" in query:
        people = query["people"]
        if not isinstance(people, list):
            people = [people]

        person_ids = [
            person
            if is_valid_uuid(person) else people_mapping.get(person, None)
            for person in people
        ]

        if None in person_ids:
            invalid_people_names = [
                people[idx] for idx, name_or_id in enumerate(person_ids) if not name_or_id
            ]
            raise ValueError(f"The following names do not exist in Immich: {invalid_people_names}")

        query["person_ids"] = person_ids
        query.pop("people", None)

    if "tags" in query:
        tags = query["tags"]
        if not isinstance(tags, list):
            tags = [tags]

        tag_ids = [
            tag
            if is_valid_uuid(tag) else tag_mapping.get(tag, None)
            for tag in tags
        ]

        if None in tag_ids:
            invalid_tags = [
                tags[idx] for idx, value_or_id in enumerate(tag_ids) if not value_or_id
            ]
            raise ValueError(f"The following tags do not exist in Immich: {invalid_tags}")

        query["tag_ids"] = tag_ids
        query.pop("tags", None)

    # use 'None' as default to simplify the product operation below
    query_countries = query.pop("country", [None])
    if isinstance(query_countries, str):
        query_countries = [query_countries]
    elif not isinstance(query_countries, list):
        raise ValueError("'country' has to be either a string or a list of strings")

    query_timespans = query.pop("timespan", [])
    if isinstance(query_timespans, dict):
        query_timespans = [query_timespans]
    elif not isinstance(query_timespans, list):
        raise ValueError("'timespan' has to be either a dict or a list of dicts")

    query_timespans = [
        {
            "before": datetime.strptime(q["end"], "%Y-%m-%d") + timedelta(hours=24),
            "after": datetime.strptime(q["start"], "%Y-%m-%d")
        }
        for q in query_timespans
    ]

    if not query_timespans:
        query_timespans.append({"before": None, "after": None})

    # for r in itertools.product(a, b): print r[0] + r[1]
    for p in itertools.product(query_countries, query_timespans):
        subquery = {
            "country": p[0],
            # unpack 'before' and 'after'
            **p[1],
            # unpack all other options, e.g. 'favorite'
            **query,
        }

        yield subquery


def is_valid_uuid(value: str) -> bool:
    try:
        return bool(uuid.UUID(value))
    except ValueError:
        return False


def valid_input_file_arg(arg: Union[Path, str]) -> Path:
    path = Path(arg).resolve()

    if not path.exists():
        raise ArgumentTypeError(f"Path does not exist: {arg}")
    if not path.is_file():
        raise ArgumentTypeError(f"Path is not a file: {arg}")

    return path


def sync_albums(args):
    # read the config and validate it against the schema
    configs = read_json(args.config_file)
    schema = read_json(Path(__file__).parent / "schema.json")
    jsonschema.validate(instance=configs, schema=schema)

    # create the api
    immich = Immich(args.immich_url, args.immich_api_key)

    # print version
    immich_version = Version(**immich.version())
    print(f"Immich version: {immich_version}")

    min_supported_version = Version(1, 126, 0)
    assert immich_version >= min_supported_version, f"Minimum supported version is {min_supported_version}"

    # prefetch all people to allow matching by name
    people = immich.get_people()
    people_name_to_id = dict((p["name"], p["id"]) for p in people["people"])

    # prefetch all tags to allow matching by name
    tags = immich.get_tags()
    tag_value_to_id = dict((t["value"], t["id"]) for t in tags)

    for config in configs:
        album_name = config["name"]
        print(f"Processing album {album_name}")

        # split the query into multiple subqueries depending on whether there are multiple
        # countries or timespans
        search_queries = list(
            config_query_to_search_queries(config["query"], people_mapping=people_name_to_id, tag_mapping=tag_value_to_id)
        )
        print(f"Album search queries: {search_queries}")

        search_results = [immich.search(**query) for query in search_queries]
        search_results = list(map(lambda x: x["assets"]["items"], search_results))
        search_results = list(itertools.chain(*search_results))

        # aggregate the asset ids from all search queries
        search_assets_ids = [asset["id"] for asset in search_results]

        # create the target album or find it amongst the other albums
        album_without_assets = create_album_if_not_exists(immich, album_name)

        # (again) retrieve the album, including it's assets
        album = immich.get_album(album_without_assets["id"], with_assets=True)
        album_assets_ids = [asset["id"] for asset in album["assets"]]

        # calculate assets missing from the album and assets which should be removed from it
        album_missing_assets_ids = list(set(search_assets_ids) - set(album_assets_ids))
        album_extra_assets_ids = list(set(album_assets_ids) - set(search_assets_ids))

        print(f"Missing assets: {len(album_missing_assets_ids)}")
        print(f"Extra assets: {len(album_extra_assets_ids)}")

        if album_extra_assets_ids:
            immich.delete_assets_from_album(album["id"], album_extra_assets_ids)

        if album_missing_assets_ids:
            immich.add_assets_to_album(album["id"], album_missing_assets_ids)

        print("Done")


def parse_args():
    parser = ArgumentParser(description="Update dynamic albums")
    parser.add_argument(
        "--immich-url",
        default=os.environ.get("IMMICH_URL", "http://localhost:2283"),
    )
    parser.add_argument(
        "--immich-api-key",
        default=os.environ.get("IMMICH_API_KEY"),
    )
    parser.add_argument(
        "--config-file",
        type=valid_input_file_arg,
        default=os.environ.get("CONFIG_FILE"),
    )
    parser.add_argument(
        "--schedule-interval",
        type=int,
        default=os.environ.get("SCHEDULE_INTERVAL", 0),
        help="Schedule interval in minutes",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    assert args.immich_api_key, "immich-api-key is required"
    assert args.config_file, "config-file is required"

    # run immediately ...
    sync_albums(args)

    # ... and then schedule a job to continuously run (optionally)
    interval_in_minutes = args.schedule_interval

    if interval_in_minutes > 0:
        print(f"Scheduling the job to run every {interval_in_minutes} minutes")
        schedule.every(interval_in_minutes).minutes.do(sync_albums, args=args)

        while True:
            schedule.run_pending()
            time.sleep(60)


if __name__ == "__main__":
    main()
