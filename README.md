# immich-dynamic-albums

Stop-gap solution for automatically creating and maintaining dynamic albums, until they are natively supported in Immich.
Dynamic albums are albums where the assets are based on some query or a rule, for example - my `favorited` pictures in `Italy` in `2023`, or all pictures of my `wife` and `me`.
Manually maintaining such albums is very tedious, hence the need for some automated way of doing it.
This has been requested in https://github.com/immich-app/immich/discussions/1673, but as of January 2024 it is not natively supported in Immich.

The current version should work with any fairly recent Immich version, but it has only been tested with v1.125.6.

## Configuration

Besides few standard configuration options (such as Immich URL and API key), the main configuration is a json file, describing the albums to be maintained - the name of the album and the search query to be used to populate the album. Here is an example showcasing all configuration features:

```json
[
    {
        # Search people by name (beware if you have people with identical names)
        "name": "Family pictures",
        "query": {
            "people": ["Me", "Wife", "Baby"]
        }
    },
    {
        # Search people by uuid
        "name": "Baby",
        "query": {
            "people": ["ee1667b6-c502-47a8-be0c-cb55be494321"]
        }
    },
    {
        # Search people by mixing names and uuids
        # Using 'people_strict_mode' will pick the assets where only the two people are tagged.
        # Assets that include any additional tagged faces will be excluded.
        "name": "Me & Wife",
        "query": {
            "people": ["Me", "35cb0ab8-24d2-4c76-bf8f-86101c867dc8"],
            "people_strict_mode": true
        }
    },
    {
        # Search tags by mixing names and uuids
        "name": "My awesome vacation",
        "query": {
            "tags": ["vacation1", "545cf3a7-9f67-4028-9ed2-54bff6508052"]
        }
    },
    {
        # Search by country, favorite flag and a timespan
        "name": "Best of Egypt 2021",
        "query": {
            "country": "Egypt",
            "favorite": true,
            "timespan": {
                "start": "2021-05-01",
                "end": "2021-05-10"
            }
        }
    },
    {
        # Search by multiple countries (names should match the ones in Immich)
        "name": "Best of Southeast Asia 2022",
        "query": {
            "country": ["Thailand", "Laos", "Cambodia", "Malaysia"],
            "favorite": true,
            "timespan": {
                "start": "2022-07-20",
                "end": "2022-08-25"
            }
        }
    },
    {
        # Search by multiple timespans
        "name": "Some random event",
        "query": {
            "timespan": [
                {"start": "2024-06-01", "end": "2024-06-03"},
                {"start": "2025-01-15", "end": "2025-01-20"}
            ]
        }
    },
    {
        # Search by path substring
        "name": "All visited football games",
        "query": {
            "path": "Football"
        }
    }
]
```

Beware that if you specify the name of an existing album, it will be overwritten. If you remove some of the albums from the config, they will not be deleted in immich - you will have to do it manually.


## Usage

### Docker Compose

```yaml
services:

    immich-server:
        container_name: immich_server
        ...

    immich-dynamic-albums:
        image: ghcr.io/kvalev/immich-dynamic-albums:${IMMICH_DYNAMIC_ALBUMS_VERSION:-latest}
        restart: unless-stopped
        volumes:
            - PATH_TO_CONFIG_JSON_FILE:/config/dynamic-albums.json:ro
        environment:
            IMMICH_URL: http://immich_server:2283/
            IMMICH_API_KEY: API_KEY
            CONFIG_FILE: /config/dynamic-albums.json
            SCHEDULE_INTERVAL: 1440 # 1440 minutes, meaning once per day
            PYTHONUNBUFFERED: True # ensure stdout is flushed on every print
        env_file:
            - .env
        depends_on:
            immich-server:
                condition: service_healthy
```

### Docker

```sh
docker run --rm \
  -v ./config/dynamic-albums.json:/config/dynamic-albums.json:ro
  -e IMMICH_URL="http://immich_server:2283/" \
  -e IMMICH_API_KEY="API_KEY" \
  -e CONFIG_FILE="/config/dynamic-albums.json" \
  -e SCHEDULE_INTERVAL="1440" \
  ghcr.io/kvalev/immich-dynamic-albums:latest
```


### CLI

Clone this repository and install the dependencies:

```sh
git clone git@github.com:kvalev/immich-dynamic-albums.git
cd immich-dynamic-albums
pip install -r requirements.txt
```

Run the script:

```sh
python sync.py --immich-url http://localhost:2283 --immich-api-key API_KEY --config-file ../config/dynamic-albums/demo-config.json
```

If you want the script to run periodically you can either use your OS scheduler or you can add the `--schedule-interval INTERVAL_IN_MINUTES`, which will sync the dynamic albums every X minutes.
