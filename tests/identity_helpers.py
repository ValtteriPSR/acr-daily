"""Verified Steam identities and isolated legacy fixtures for server tests."""
import secrets
import time
from seasons import steam_finish, _new_session
from steam_auth import digest


def register_member(store, nickname):
    pending = secrets.token_urlsafe(32)
    steam_id = str(76561198000000000 + secrets.randbelow(999999999))
    store.db.execute('INSERT INTO steam_pending_sessions(session_hash,steam_id,expires) VALUES(?,?,?)',
                     (digest(pending), steam_id, time.time()+60))
    return steam_finish(store, pending, nickname)


def legacy_member(store, nickname):
    # Simulate an existing pre-Steam database, without exposing a legacy login API.
    row = store.db.execute('INSERT INTO club_members(nickname,nickname_key,recovery_hash,created) VALUES(?,?,?,?)',
                           (nickname, nickname.casefold(), 'obsolete-legacy-hash', time.time()))
    return {'token': _new_session(store, row.lastrowid), 'memberId': row.lastrowid}
