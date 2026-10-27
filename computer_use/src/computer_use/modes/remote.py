"""Remote desktop mode — host client window + visual loop (Phase 3)."""


def default_remote_controller():
    from computer_use.controllers.remote_controller import RemoteController, get_remote_enumerator

    return RemoteController(enumerator=get_remote_enumerator())
