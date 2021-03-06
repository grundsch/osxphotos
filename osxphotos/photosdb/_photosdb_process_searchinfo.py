""" Methods for PhotosDB to add Photos 5 search info such as machine learning labels 
    Kudos to Simon Willison who figured out how to extract this data from psi.sql
    ref: https://github.com/dogsheep/photos-to-sqlite/issues/16
"""

import logging
import pathlib
import uuid as uuidlib
from pprint import pformat

from .._constants import _PHOTOS_4_VERSION, SEARCH_CATEGORY_LABEL
from ..utils import _db_is_locked, _debug, _open_sql_file

"""
    This module should be imported in the class defintion of PhotosDB in photosdb.py
    Do not import this module directly
    This module adds the following method to PhotosDB:
        _process_searchinfo: process search terms from psi.sqlite 

    The following properties are added to PhotosDB    
        labels: list of all labels in the library
        labels_normalized: list of all labels normalized in the library  
        labels_as_dict: dict of {label: count of photos} in reverse sorted order (most photos first)
        labels_normalized_as_dict: dict of {normalized label: count of photos} in reverse sorted order (most photos first)

    The following data structures are added to PhotosDB
        self._db_searchinfo_categories
        self._db_searchinfo_uuid
        self._db_searchinfo_labels 
        self._db_searchinfo_labels_normalized 
    
    These methods only work on Photos 5 databases.  Will print warning on earlier library versions.
"""


def _process_searchinfo(self):
    """ load machine learning/search term label info from a Photos library
        db_connection: a connection to the SQLite database file containing the 
        search terms.  In Photos 5, this is called psi.sqlite
        Note: Only works on Photos version == 5.0 """

    if self._db_version <= _PHOTOS_4_VERSION:
        raise NotImplementedError(
            f"search info not implemented for this database version"
        )

    search_db_path = pathlib.Path(self._dbfile).parent / "search" / "psi.sqlite"
    if not search_db_path.exists():
        raise FileNotFoundError(f"could not find search db: {search_db_path}")

    if _db_is_locked(search_db_path):
        search_db = self._copy_db_file(search_db_path)
    else:
        search_db = search_db_path

    (conn, c) = _open_sql_file(search_db)

    result = conn.execute(
        """
        select
        ga.rowid,
        assets.uuid_0,
        assets.uuid_1,
        groups.rowid as groupid,
        groups.category,
        groups.owning_groupid,
        groups.content_string,
        groups.normalized_string,
        groups.lookup_identifier
        from
        ga
        join groups on groups.rowid = ga.groupid
        join assets on ga.assetid = assets.rowid
        order by
        ga.rowid
        """
    )

    # _db_searchinfo_uuid is dict in form {uuid : [list of associated search info records]
    _db_searchinfo_uuid = {}

    # _db_searchinfo_categories is dict in form {search info category id: list normalized strings for the category
    # right now, this is mostly for debugging to easily see which search terms are in the library
    _db_searchinfo_categories = {}

    # _db_searchinfo_labels is dict in form {normalized label: [list of photo uuids]}
    # this serves as a reverse index from label to photos containing the label
    # _db_searchinfo_labels_normalized is the same but with normalized (lower case) version of the label
    _db_searchinfo_labels = {}
    _db_searchinfo_labels_normalized = {}

    cols = [c[0] for c in result.description]
    for row in result.fetchall():
        record = dict(zip(cols, row))
        uuid = ints_to_uuid(record["uuid_0"], record["uuid_1"])
        # strings have null character appended, so strip it
        for key in record:
            if isinstance(record[key], str):
                record[key] = record[key].replace("\x00", "")
        try:
            _db_searchinfo_uuid[uuid].append(record)
        except KeyError:
            _db_searchinfo_uuid[uuid] = [record]

        category = record["category"]
        try:
            _db_searchinfo_categories[record["category"]].append(
                record["normalized_string"]
            )
        except KeyError:
            _db_searchinfo_categories[record["category"]] = [
                record["normalized_string"]
            ]

        if record["category"] == SEARCH_CATEGORY_LABEL:
            label = record["content_string"]
            label_norm = record["normalized_string"]
            try:
                _db_searchinfo_labels[label].append(uuid)
                _db_searchinfo_labels_normalized[label_norm].append(uuid)
            except KeyError:
                _db_searchinfo_labels[label] = [uuid]
                _db_searchinfo_labels_normalized[label_norm] = [uuid]

    self._db_searchinfo_categories = _db_searchinfo_categories
    self._db_searchinfo_uuid = _db_searchinfo_uuid
    self._db_searchinfo_labels = _db_searchinfo_labels
    self._db_searchinfo_labels_normalized = _db_searchinfo_labels_normalized

    if _debug():
        logging.debug(
            "_db_searchinfo_categories: \n" + pformat(self._db_searchinfo_categories)
        )
        logging.debug("_db_searchinfo_uuid: \n" + pformat(self._db_searchinfo_uuid))
        logging.debug("_db_searchinfo_labels: \n" + pformat(self._db_searchinfo_labels))
        logging.debug(
            "_db_searchinfo_labels_normalized: \n"
            + pformat(self._db_searchinfo_labels_normalized)
        )


@property
def labels(self):
    """ return list of all search info labels found in the library """
    if self._db_version <= _PHOTOS_4_VERSION:
        logging.warning(f"SearchInfo not implemented for this library version")
        return []

    return list(self._db_searchinfo_labels.keys())


@property
def labels_normalized(self):
    """ return list of all normalized search info labels found in the library """
    if self._db_version <= _PHOTOS_4_VERSION:
        logging.warning(f"SearchInfo not implemented for this library version")
        return []

    return list(self._db_searchinfo_labels_normalized.keys())


@property
def labels_as_dict(self):
    """ return labels as dict of label: count in reverse sorted order (descending) """
    if self._db_version <= _PHOTOS_4_VERSION:
        logging.warning(f"SearchInfo not implemented for this library version")
        return dict()

    labels = {k: len(v) for k, v in self._db_searchinfo_labels.items()}
    labels = dict(sorted(labels.items(), key=lambda kv: kv[1], reverse=True))
    return labels


@property
def labels_normalized_as_dict(self):
    """ return normalized labels as dict of label: count in reverse sorted order (descending) """
    if self._db_version <= _PHOTOS_4_VERSION:
        logging.warning(f"SearchInfo not implemented for this library version")
        return dict()
    labels = {k: len(v) for k, v in self._db_searchinfo_labels_normalized.items()}
    labels = dict(sorted(labels.items(), key=lambda kv: kv[1], reverse=True))
    return labels


# The following method is not imported into PhotosDB


def ints_to_uuid(uuid_0, uuid_1):
    """ convert two signed ints into a UUID strings
        uuid_0, uuid_1: the two int components of an RFC 4122 UUID """

    # assumes uuid imported as uuidlib (to avoid namespace conflict with other uses of uuid)

    bytes_ = uuid_0.to_bytes(8, "little", signed=True) + uuid_1.to_bytes(
        8, "little", signed=True
    )
    return str(uuidlib.UUID(bytes=bytes_)).upper()
