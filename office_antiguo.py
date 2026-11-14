"""Conversión local temporal de Office 97–2003 con Office instalado."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

FORMATOS_ANTIGUOS = {'.doc': '.docx', '.xls': '.xlsx', '.ppt': '.pptx'}


@contextmanager
def convertir_antiguo(origen):
    import pythoncom
    from win32com.client import DispatchEx

    origen = Path(origen).resolve()
    extension = origen.suffix.lower()
    programa = {'.doc': 'Word.Application', '.xls': 'Excel.Application',
                '.ppt': 'PowerPoint.Application'}[extension]
    pythoncom.CoInitialize()
    aplicacion = documento = None
    try:
        with TemporaryDirectory(prefix='anonimizador-office-') as carpeta:
            destino = Path(carpeta) / ('convertido' + FORMATOS_ANTIGUOS[extension])
            try:
                # Instancia independiente: no se cierran documentos del usuario.
                aplicacion = DispatchEx(programa)
                aplicacion.AutomationSecurity = 3  # No ejecutar macros.
                if extension == '.doc':
                    aplicacion.Visible = False
                    aplicacion.DisplayAlerts = 0
                    aplicacion.Options.UpdateLinksAtOpen = False
                    documento = aplicacion.Documents.Open(
                        FileName=str(origen), ConfirmConversions=False, ReadOnly=True,
                        AddToRecentFiles=False, Visible=False, NoEncodingDialog=True,
                        PasswordDocument='', WritePasswordDocument='')
                    documento.SaveAs2(str(destino), FileFormat=12)
                elif extension == '.xls':
                    aplicacion.Visible = False
                    aplicacion.DisplayAlerts = False
                    aplicacion.EnableEvents = False
                    aplicacion.AskToUpdateLinks = False
                    documento = aplicacion.Workbooks.Open(
                        str(origen), UpdateLinks=0, ReadOnly=True, Password='',
                        WriteResPassword='', IgnoreReadOnlyRecommended=True, AddToMru=False)
                    documento.SaveAs(str(destino), FileFormat=51)
                else:
                    aplicacion.DisplayAlerts = 1
                    documento = aplicacion.Presentations.Open(
                        str(origen), ReadOnly=True, Untitled=False, WithWindow=False)
                    documento.SaveAs(str(destino), FileFormat=24)
                if not destino.is_file():
                    raise ValueError('No se generó la conversión.')
            except Exception as exc:
                raise ValueError(
                    'No se pudo convertir el documento antiguo. Requiere Microsoft Office '
                    'instalado y un archivo válido sin contraseña. El original se conserva.'
                ) from exc
            finally:
                if documento is not None:
                    try:
                        if extension == '.ppt':
                            documento.Close()
                        else:
                            documento.Close(SaveChanges=False)
                    except Exception:
                        pass
                if aplicacion is not None:
                    try:
                        aplicacion.Quit()
                    except Exception:
                        pass
            yield destino
    finally:
        pythoncom.CoUninitialize()
