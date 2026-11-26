"""Control transaccional seguro de claves foráneas SQLite (etapa 3D.4C.5D.4).

Módulo aislado: recibe una ``sqlite3.Connection`` externa que NO abre, NO cierra y
NO configura más allá de lo descrito. No conoce rutas, no importa ``database`` ni
el servicio de backup y no se integra al arranque.

Arquitectura
============

El módulo es el único dueño de la transacción. La operación (y el gancho previo al
backup) NO reciben la conexión real: la operación recibe una ``ConexionRestringida``
que solo expone ``execute``, ``executemany`` y ``cursor``; los cursores que devuelve
solo exponen ``execute``/``executemany``/``fetch*``/iteración/``rowcount``/
``lastrowid``/``description``/``close`` y NO tienen ``connection``. No existen
``commit``, ``rollback``, ``close``, ``set_authorizer``, ``autocommit``,
``isolation_level``, ``executescript`` ni ``in_transaction``. El gancho previo al
backup no recibe ninguna conexión.

Esta interfaz previene ERRORES ACCIDENTALES del código propio. NO es aislamiento frente
a código Python malicioso: quien conserve una referencia a la conexión real (por
ejemplo, por una clausura) sigue pudiendo usarla. Como defensa adicional, el
autorizador de SQLite deniega BEGIN/COMMIT/END/ROLLBACK, ATTACH/DETACH, los SAVEPOINT
reservados del mecanismo y las escrituras de ``foreign_keys``, ``journal_mode``,
``writable_schema``, ``locking_mode``, ``synchronous``, ``user_version``,
``application_id``, ``schema_version`` y ``query_only``. SAVEPOINT/RELEASE propios del
llamador siguen permitidos porque no pueden terminar la transacción externa.

Secuencia (``ejecutar_con_claves_foraneas_controladas``)
========================================================

1. Precondiciones, sin modificar nada: conexión abierta, ``autocommit`` heredado,
   sin transacción abierta, sin bases adjuntas, ``query_only`` apagado,
   ``foreign_keys=ON``, ``foreign_key_check`` vacío y ``quick_check`` = ok.
2. ``PRAGMA foreign_keys=OFF`` fuera de la transacción, verificado en 0.
3. ``BEGIN IMMEDIATE`` (reserva de escritura) y SAVEPOINT centinela con nombre secreto.
4. Revalidación de ``foreign_key_check`` y ``quick_check`` bajo la reserva.
5. Gancho ``antes_de_operar()`` (sin argumentos) con ``query_only=ON`` y un autorizador
   de solo lectura sobre la conexión de escritura; ambos se retiran después.
6. Autorizador de operación y ``operacion(conexion_restringida)``; la interfaz se
   invalida al terminar y el autorizador se retira.
7. Verificación de continuidad: transacción abierta, ``autocommit`` e
   ``isolation_level`` sin cambios, sin bases adjuntas y ``RELEASE`` del centinela. El
   centinela solo existe dentro de la transacción original: si la transacción fue
   terminada (COMMIT, ROLLBACK, ``OR ROLLBACK``, ``RAISE(ROLLBACK)``) y se abrió otra,
   el ``RELEASE`` falla y el estado se declara incierto.
8. ``foreign_key_check`` y ``quick_check`` finales y nueva verificación de estado.
9. ``commit`` y verificación de que la transacción terminó.
10. Rollback si hubo error; restauración y verificación de ``foreign_keys=ON`` siempre.

Estados de confirmación (``confirmada``)
========================================

* ``True``: ``commit()`` retornó sin error y la transacción quedó cerrada con el modo de
  transacciones intacto.
* ``False``: no hubo ``commit`` y se comprobó la continuidad de la transacción original
  (centinela liberado, sin cambio de modo ni de bases adjuntas), de modo que ningún cambio
  pudo persistir; o bien el fallo ocurrió antes de que se abriera ninguna transacción.
* ``None``: cualquier otro caso (conexión cerrada o transacción perdida, autocommit o
  aislamiento alterados, centinela ausente, fallo al retirar el autorizador, commit que
  deja la transacción cerrada con error, etc.). La conexión NO es apta. Ni
  ``PRAGMA data_version`` ni ``total_changes`` se usan como prueba.

Toda excepción lleva ``confirmada``, ``conexion_apta`` y ``fase``. La excepción original
se conserva en ``__cause__``; los fallos del rollback o de la restauración se añaden como
notas. Las excepciones que no heredan de ``Exception`` (por ejemplo KeyboardInterrupt) se
re-lanzan sin envolver, tras el rollback y la restauración.

Precondiciones que Python NO permite verificar (responsabilidad del llamador)
=============================================================================

* La conexión no tiene un autorizador previo: no puede consultarse y el mecanismo lo
  reemplaza y lo elimina al terminar (cualquier restricción previa deja de aplicar).
* Ninguna otra referencia a la conexión real usará la conexión durante la operación.
* No hay ``set_trace_callback``/``set_progress_handler`` ni ``row_factory`` que alteren
  la ejecución, y ningún otro hilo la usa.

Por eso se recomienda una CONEXIÓN EXCLUSIVA PARA MIGRACIONES: recién abierta, sin
autorizador, sin bases adjuntas, con modo de transacciones heredado, no compartida y
descartada ante cualquier error (``conexion_apta=False``).

Limitaciones documentadas
=========================

* Código que obtenga la conexión real puede retirar el autorizador y hacer commits
  anticipados; el mecanismo lo detecta por el centinela y lo informa como incierto, pero
  no puede impedirlo ni deshacer lo ya confirmado.
* ``crear_base(conexion=...)`` exige una ``sqlite3.Connection`` real y por tanto es
  INCOMPATIBLE con la interfaz restringida. No se flexibilizó la protección para
  forzarlo; una etapa posterior deberá aportar una migración que use esta interfaz.
* El gancho previo no recibe la conexión de escritura: el backup debe usar su propia
  conexión de solo lectura, que puede leer bajo la reserva en DELETE y WAL.
* No hay transacción alguna entre las precondiciones y ``BEGIN IMMEDIATE``; por eso se
  revalida todo bajo la reserva.
"""

import secrets
import sqlite3
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Optional

_LEGACY = getattr(sqlite3, "LEGACY_TRANSACTION_CONTROL", -1)
_PRAGMAS_PROTEGIDOS = frozenset({
    "foreign_keys", "journal_mode", "writable_schema", "locking_mode", "synchronous",
    "user_version", "application_id", "schema_version", "query_only",
})
_PREFIJO_CENTINELA = "_fm_ctl_"
_BASES_PERMITIDAS = frozenset({"main", "temp"})
_ACCIONES_LECTURA = frozenset({
    sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", sqlite3.SQLITE_SELECT),
})


class ErrorControlClavesForaneas(RuntimeError):
    """Base: ``confirmada`` (True/False/None), ``conexion_apta`` y ``fase``."""

    confirmada: Optional[bool] = None
    conexion_apta: bool = False

    def __init__(self, fase, mensaje, *, conexion_apta):
        super().__init__(f"Control de claves foráneas: {mensaje} (fase '{fase}').")
        self.fase = fase
        self.conexion_apta = conexion_apta


class ErrorAntesDeConfirmar(ErrorControlClavesForaneas):
    """Se comprobó que nada quedó confirmado. ``conexion_apta`` es False si falló el rollback o la restauración."""

    confirmada = False


class ErrorDespuesDeConfirmar(ErrorControlClavesForaneas):
    """Los cambios SÍ quedaron confirmados, pero la conexión no se restauró: no debe reutilizarse."""

    confirmada = True


class ErrorEstadoIncierto(ErrorControlClavesForaneas):
    """No puede afirmarse si los cambios persistieron. La conexión no es apta."""

    confirmada = None


@dataclass(frozen=True)
class ResultadoControlClavesForaneas:
    confirmada: bool
    resultado: Any = None


class _Rechazo(Exception):
    """Fallo controlado propio; su texto nunca incluye rutas ni datos."""


class _Incierto(_Rechazo):
    """El estado de la transacción ya no puede garantizarse."""


class _Vigencia:
    __slots__ = ("activa",)

    def __init__(self):
        self.activa = True


class CursorRestringido:
    """Cursor sin ``connection``: no permite recuperar la conexión real."""

    __slots__ = ("_cursor", "_vigencia")

    def __init__(self, cursor, vigencia):
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_vigencia", vigencia)

    def _comprobar(self):
        if not self._vigencia.activa:
            raise sqlite3.ProgrammingError("La interfaz restringida ya no está vigente.")

    def execute(self, sql, parameters=(), /):
        self._comprobar()
        self._cursor.execute(sql, parameters)
        return self

    def executemany(self, sql, seq_of_parameters, /):
        self._comprobar()
        self._cursor.executemany(sql, seq_of_parameters)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchmany(self, size=None):
        return self._cursor.fetchmany() if size is None else self._cursor.fetchmany(size)

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        self._cursor.close()

    def __iter__(self):
        return iter(self._cursor)

    def __next__(self):
        return next(self._cursor)

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def description(self):
        return self._cursor.description


class ConexionRestringida:
    """Interfaz entregada a la operación: solo ejecuta sentencias SQL."""

    __slots__ = ("_conexion", "_vigencia")

    def __init__(self, conexion, vigencia):
        object.__setattr__(self, "_conexion", conexion)
        object.__setattr__(self, "_vigencia", vigencia)

    def _comprobar(self):
        if not self._vigencia.activa:
            raise sqlite3.ProgrammingError("La interfaz restringida ya no está vigente.")

    def execute(self, sql, parameters=(), /):
        self._comprobar()
        return CursorRestringido(self._conexion.execute(sql, parameters), self._vigencia)

    def executemany(self, sql, seq_of_parameters, /):
        self._comprobar()
        cursor = self._conexion.cursor()
        cursor.executemany(sql, seq_of_parameters)
        return CursorRestringido(cursor, self._vigencia)

    def cursor(self):
        self._comprobar()
        return CursorRestringido(self._conexion.cursor(), self._vigencia)


def _es_centinela(nombre):
    return str(nombre).casefold().startswith(_PREFIJO_CENTINELA)


def _autorizador_operacion(accion, arg1, arg2, base, origen):
    if accion in (sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    if accion == sqlite3.SQLITE_SAVEPOINT and _es_centinela(arg2):
        return sqlite3.SQLITE_DENY
    if accion == sqlite3.SQLITE_PRAGMA and arg2 is not None and str(arg1).casefold() in _PRAGMAS_PROTEGIDOS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _autorizador_lectura(accion, arg1, arg2, base, origen):
    if accion in _ACCIONES_LECTURA:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _foreign_keys(conexion):
    fila = conexion.execute("PRAGMA foreign_keys").fetchone()
    return None if fila is None else fila[0]


def _query_only(conexion):
    fila = conexion.execute("PRAGMA query_only").fetchone()
    return None if fila is None else fila[0]


def _validar_integridad(conexion):
    if conexion.execute("PRAGMA foreign_key_check").fetchall():
        raise _Rechazo("foreign_key_check")
    if conexion.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
        raise _Rechazo("quick_check")


def _en_transaccion(conexion):
    try:
        return conexion.in_transaction
    except sqlite3.ProgrammingError:
        return None


def _bases_adjuntas(conexion):
    nombres = {fila[1] for fila in conexion.execute("PRAGMA database_list").fetchall()}
    return nombres - _BASES_PERMITIDAS


def _verificar_precondiciones(conexion):
    if getattr(conexion, "autocommit", _LEGACY) != _LEGACY:
        raise _Rechazo("autocommit_no_heredado")
    if _en_transaccion(conexion) is not False:
        raise _Rechazo("transaccion_previa_o_conexion_cerrada")
    if _bases_adjuntas(conexion):
        raise _Rechazo("bases_adjuntas")
    if _query_only(conexion) != 0:
        raise _Rechazo("query_only_activo")
    if _foreign_keys(conexion) != 1:
        raise _Rechazo("foreign_keys_inicial_no_activo")
    _validar_integridad(conexion)
    if _en_transaccion(conexion) is not False:
        raise _Rechazo("transaccion_abierta_por_las_validaciones")


def _verificar_estado(conexion, ctx):
    estado = _en_transaccion(conexion)
    if estado is None:
        raise _Incierto("conexion_cerrada")
    if estado is False:
        raise _Incierto("transaccion_finalizada")
    if getattr(conexion, "autocommit", _LEGACY) != _LEGACY:
        raise _Incierto("autocommit_alterado")
    if conexion.isolation_level != ctx.aislamiento:
        raise _Incierto("isolation_level_alterado")
    if _bases_adjuntas(conexion):
        raise _Incierto("bases_adjuntas")


def _verificar_continuidad(conexion, ctx):
    """Comprueba que sigue vigente la transacción original (centinela) y libera el centinela."""
    _verificar_estado(conexion, ctx)
    if ctx.centinela_activo:
        try:
            conexion.execute(f"RELEASE {ctx.centinela}")
        except sqlite3.Error as fallo:
            raise _Incierto("centinela_perdido") from fallo
        ctx.centinela_activo = False


def _instalar_autorizador(conexion, ctx, autorizador):
    conexion.set_authorizer(autorizador)
    ctx.autorizador_instalado = True


def _retirar_autorizador(conexion, ctx):
    if ctx.autorizador_instalado:
        conexion.set_authorizer(None)
        ctx.autorizador_instalado = False


def _restaurar_query_only(conexion, ctx):
    if ctx.query_only_activado:
        conexion.execute("PRAGMA query_only=OFF")
        if _query_only(conexion) != 0:
            raise _Rechazo("restauracion_query_only_no_efectiva")
        ctx.query_only_activado = False


def _ejecutar_gancho(conexion, antes_de_operar, ctx):
    ctx.query_only_activado = True
    conexion.execute("PRAGMA query_only=ON")
    if _query_only(conexion) != 1:
        raise _Rechazo("query_only_no_efectivo")
    _instalar_autorizador(conexion, ctx, _autorizador_lectura)
    try:
        antes_de_operar()
    finally:
        _retirar_autorizador(conexion, ctx)
        _restaurar_query_only(conexion, ctx)
    _verificar_estado(conexion, ctx)


def _fases(conexion, operacion, antes_de_operar, ctx):
    ctx.fase = "desactivar_claves_foraneas"
    ctx.fk_desactivadas = True
    conexion.execute("PRAGMA foreign_keys=OFF")
    if _foreign_keys(conexion) != 0:
        raise _Rechazo("desactivacion_no_efectiva")
    ctx.fase = "reserva_de_escritura"
    conexion.execute("BEGIN IMMEDIATE")
    ctx.transaccion_iniciada = True
    ctx.fase = "centinela"
    conexion.execute(f"SAVEPOINT {ctx.centinela}")
    ctx.centinela_activo = True
    ctx.fase = "revalidacion_bajo_reserva"
    _validar_integridad(conexion)
    if antes_de_operar is not None:
        ctx.fase = "antes_de_operar"
        _ejecutar_gancho(conexion, antes_de_operar, ctx)
    ctx.fase = "operacion"
    vigencia = _Vigencia()
    _instalar_autorizador(conexion, ctx, _autorizador_operacion)
    try:
        ctx.resultado = operacion(ConexionRestringida(conexion, vigencia))
    finally:
        vigencia.activa = False
        _retirar_autorizador(conexion, ctx)
    ctx.fase = "verificar_transaccion"
    _verificar_continuidad(conexion, ctx)
    ctx.fase = "validacion_final"
    _validar_integridad(conexion)
    ctx.fase = "verificar_antes_del_commit"
    _verificar_estado(conexion, ctx)
    ctx.fase = "commit"
    ctx.commit_intentado = True
    conexion.commit()
    ctx.fase = "verificar_commit"
    if _en_transaccion(conexion) is not False or getattr(conexion, "autocommit", _LEGACY) != _LEGACY:
        raise _Incierto("commit_sin_evidencia")
    ctx.confirmada = True


def ejecutar_con_claves_foraneas_controladas(
    conexion: sqlite3.Connection,
    operacion: Callable[[ConexionRestringida], Any],
    *,
    antes_de_operar: Optional[Callable[[], Any]] = None,
) -> ResultadoControlClavesForaneas:
    if not isinstance(conexion, sqlite3.Connection):
        raise TypeError("Se requiere una sqlite3.Connection.")
    if not callable(operacion) or (antes_de_operar is not None and not callable(antes_de_operar)):
        raise TypeError("La operación y el gancho previo deben ser invocables.")

    try:
        _verificar_precondiciones(conexion)
        aislamiento = conexion.isolation_level
    except BaseException as fallo:
        if not isinstance(fallo, Exception):
            raise
        # No se tocó nada: la conexión conserva exactamente su estado original.
        raise ErrorAntesDeConfirmar(
            "precondiciones", "precondición no satisfecha", conexion_apta=_en_transaccion(conexion) is not None
        ) from fallo

    ctx = SimpleNamespace(
        fase="precondiciones", aislamiento=aislamiento, centinela=_PREFIJO_CENTINELA + secrets.token_hex(8),
        centinela_activo=False, fk_desactivadas=False, transaccion_iniciada=False, autorizador_instalado=False,
        query_only_activado=False, commit_intentado=False, confirmada=False, resultado=None,
    )
    incierto = False
    error = None
    notas = []
    try:
        _fases(conexion, operacion, antes_de_operar, ctx)
    except BaseException as fallo:
        error = fallo
        incierto = isinstance(fallo, _Incierto)

    if ctx.autorizador_instalado:
        try:
            _retirar_autorizador(conexion, ctx)
        except BaseException as fallo:
            incierto = True
            notas.append(f"No se pudo retirar el autorizador: {type(fallo).__name__}.")

    if error is not None and not incierto:
        if ctx.commit_intentado:
            if _en_transaccion(conexion) is not True:
                incierto = True
        elif ctx.transaccion_iniciada:
            try:
                _verificar_continuidad(conexion, ctx)
            except BaseException:
                incierto = True

    if error is not None and _en_transaccion(conexion):
        try:
            if incierto:
                conexion.execute("ROLLBACK")
            else:
                conexion.rollback()
        except BaseException as fallo:
            notas.append(f"No se pudo revertir: {type(fallo).__name__}.")

    if ctx.query_only_activado:
        try:
            _restaurar_query_only(conexion, ctx)
        except BaseException as fallo:
            notas.append(f"No se restauró query_only: {type(fallo).__name__}.")

    fallo_restauracion = None
    if ctx.fk_desactivadas:
        try:
            conexion.execute("PRAGMA foreign_keys=ON")
            if _foreign_keys(conexion) != 1:
                raise _Rechazo("restauracion_no_efectiva")
        except BaseException as fallo:
            fallo_restauracion = fallo
            notas.append(f"No se restauró foreign_keys=ON: {type(fallo).__name__}.")

    if error is None:
        if fallo_restauracion is not None or notas:
            envuelta = ErrorDespuesDeConfirmar(
                "restaurar_claves_foraneas",
                "los cambios fueron CONFIRMADOS pero no se restauró el estado de la conexión; la conexión no es apta",
                conexion_apta=False,
            )
            for nota in notas:
                envuelta.add_note(nota)
            raise envuelta from fallo_restauracion
        return ResultadoControlClavesForaneas(confirmada=True, resultado=ctx.resultado)

    if not isinstance(error, Exception):
        for nota in notas:
            error.add_note(nota)
        raise error

    if incierto:
        envuelta = ErrorEstadoIncierto(
            ctx.fase, "no puede afirmarse si los cambios persistieron; la conexión no es apta", conexion_apta=False
        )
    else:
        apta = not notas and _en_transaccion(conexion) is False
        envuelta = ErrorAntesDeConfirmar(ctx.fase, "los cambios no se confirmaron", conexion_apta=apta)
    for nota in notas:
        envuelta.add_note(nota)
    raise envuelta from error
