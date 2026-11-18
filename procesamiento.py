"""Cancelación local compartida por las etapas de una operación del hilo."""
from contextlib import contextmanager
from contextvars import ContextVar


class ProcessingCancelled(Exception):
    pass


_cancel_event = ContextVar('cancel_event', default=None)


def check_cancelled():
    event = _cancel_event.get()
    if event is not None and event.is_set():
        raise ProcessingCancelled('Anonimización cancelada por el sustanciador.')


@contextmanager
def cancellation_scope(event):
    token = _cancel_event.set(event)
    try:
        check_cancelled()
        yield
    finally:
        _cancel_event.reset(token)
