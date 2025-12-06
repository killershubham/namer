import requests
from loguru import logger
from typing import Optional, List, Any, Dict
from namer.configuration import NamerConfig
from namer.comparison_results import LookedUpFileInfo, SceneType, Performer
from namer.fileinfo import FileInfo

def __get_stash_headers(config: NamerConfig) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if config.stash_api_key:
        headers["ApiKey"] = config.stash_api_key
    return headers

def __map_stash_to_namer(data: Dict[str, Any]) -> LookedUpFileInfo:
    """
    Maps a StashDB JSON response to Namer's internal LookedUpFileInfo object.
    """
    info = LookedUpFileInfo()
    info.db_source = "stashdb" # <--- Set source to stashdb
    info._id = data.get('id')  # <--- Store the Stash ID
    # Stash IDs are UUIDs. We prefix to avoid collision if mixed with TPDB later.
    info.uuid = f"stashdb:{data.get('id')}" 
    info.name = data.get('title')
    info.description = data.get('details')
    info.date = data.get('date')
    
    # Map Studio
    studio = data.get('studio')
    if studio:
        info.site = studio.get('name')
        
    # Map Performers
    for p in data.get('performers', []):
        performer = Performer(p.get('name'))
        # Try to get performer image
        if p.get('image_path'):
            performer.image = p.get('image_path')
        info.performers.append(performer)
        
    # Map Tags
    for t in data.get('tags', []):
        info.tags.append(t.get('name'))
    
    # Map Poster/Image
    # StashDB structure usually has 'paths' -> 'screenshot' or 'images' -> list
    if data.get('paths') and data['paths'].get('screenshot'):
        info.poster_url = data['paths']['screenshot']
    elif data.get('images') and len(data['images']) > 0:
        info.poster_url = data['images'][0]['url']

    info.type = SceneType.SCENE
    # Since this came from a hash match, we assume it's part of the collection/db
    info.is_collected = True 
    
    # Fake a high match score for internal logic since Hash is exact
    info.original_query = "StashDB_OSHash_Match"
    
    return info

def search_stash_by_oshash(oshash: str, config: NamerConfig) -> Optional[LookedUpFileInfo]:
    """
    Searches StashDB using the OpenSubtitles Hash (OSHash).
    """
    if not oshash or not config.stash_enabled:
        return None

    logger.info(f"Matching against StashDB via OSHash: {oshash}")

    # GraphQL query
    query = """
    query FindSceneByHash($input: SceneHashInput!) {
      findSceneByHash(input: $input) {
        id
        title
        details
        date
        studio {
          name
        }
        performers {
          name
          image_path
        }
        tags {
          name
        }
        paths {
          screenshot
        }
        images {
          url
        }
      }
    }
    """
    
    variables = {
        "input": {
            "oshash": oshash
        }
    }

    try:
        response = requests.post(
            config.stash_url,
            json={'query': query, 'variables': variables},
            headers=__get_stash_headers(config),
            timeout=10
        )
        
        if response.status_code == 200:
            json_data = response.json()
            if json_data.get('data') and json_data['data'].get('findSceneByHash'):
                scene_data = json_data['data']['findSceneByHash']
                logger.info(f"Match found in StashDB: {scene_data.get('title')}")
                return __map_stash_to_namer(scene_data)
            else:
                logger.info("No match in StashDB")
        else:
            logger.warning(f"StashDB returned status {response.status_code}: {response.text}")
            
    except Exception as e:
        logger.error(f"Error querying StashDB: {e}")

    return None

def search_stash_by_query(file_info: FileInfo, config: NamerConfig) -> List[LookedUpFileInfo]:
    """
    Searches StashDB using a fuzzy string query (Site + Title).
    """
    if not config.stash_enabled:
        return []

    # Construct a search term
    search_term = ""
    if file_info.site:
        search_term += f"{file_info.site} "
    if file_info.name:
        search_term += file_info.name
    
    search_term = search_term.strip()
    if not search_term:
        return []

    logger.info(f"Matching against StashDB via text query: '{search_term}'")

    query = """
    query FindScenes($term: String!) {
      findScenes(scene_filter: {search: $term, per_page: 5}) {
        scenes {
          id
          title
          details
          date
          studio {
            name
          }
          performers {
            name
            image_path
          }
          tags {
            name
          }
          paths {
            screenshot
          }
        }
      }
    }
    """

    variables = {"term": search_term}

    try:
        response = requests.post(
            config.stash_url,
            json={'query': query, 'variables': variables},
            headers=__get_stash_headers(config),
            timeout=10
        )

        results = []
        if response.status_code == 200:
            json_data = response.json()
            if json_data.get('data') and json_data['data'].get('findScenes'):
                scenes = json_data['data']['findScenes']['scenes']
                logger.info(f"StashDB found {len(scenes)} potential matches via text query")
                for scene in scenes:
                    results.append(__map_stash_to_namer(scene))
            else:
                logger.info("No match in StashDB via text query")
        
        return results

    except Exception as e:
        logger.error(f"Error querying StashDB: {e}")
        return []