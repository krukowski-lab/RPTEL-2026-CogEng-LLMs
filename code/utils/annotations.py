def get_relevant_ids(db) -> dict:
    """Fetches comment IDs grouped by project for comments that have been annotated by both annotators."""
    annotations = list(db.annotations.find({
        "$and": [
            {"annotations": {"$exists": True}},
            {"$expr": {"$gt": [{"$size": "$annotations"}, 0]}},
            {"annotations.completed_by": 2},
            {"annotations.completed_by": 3},
        ]
    },
        {
            "data": 1,
            "project_title": 1
        }))
    print(f"Fetched comments have length {len(annotations)}")
    rel_comment_ids = {}
    for elem in annotations:
        title = elem['project_title']
        id_com = elem['data'].get('id_com', None) if elem['data'].get('id_com', None) is not None else elem['data'].get('id', None)
        if title not in rel_comment_ids.keys():
            rel_comment_ids[title] = set()
            rel_comment_ids[title].add(id_com)
        elif title in rel_comment_ids.keys():
            rel_comment_ids[title].add(id_com)
    for k, v in rel_comment_ids.items():
        rel_comment_ids[k] = list(v)
    return rel_comment_ids
