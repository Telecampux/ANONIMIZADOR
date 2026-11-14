# Anonimizador y restauración local del fallo

Requiere Windows y Python 3.13. `Instalar.bat` instala dependencias y modelos; `Iniciar.bat` abre la aplicación. El procesamiento y las tablas permanecen en el computador.

1. Crea un **Nuevo caso** con un nombre o elige uno en **Abrir caso local**. La carga de archivos se habilita cuando hay un caso activo.
2. Pulsa **Demanda y anexos de la tutela…**, carga los documentos y marca el archivo que quieras analizar.
3. Pulsa **Iniciar anonimización**. Al terminar, la pantalla principal muestra todos los nombres, identificaciones y correos detectados, agrupados y con su casilla. Ningún dato aparece premarcado. Marca únicamente los datos que deseas ocultar y pulsa **Anonimizar campos seleccionados** para comparar la copia.

4. La copia para el skill se genera en **DOCX con texto**, usando códigos únicos por caso, por ejemplo `[PERSONA_A1B2C3D4E5F6_001]`. El mismo valor, ignorando diferencias de mayúsculas, mantiene el código en los anexos. Variantes ortográficas o nombres abreviados no se fusionan automáticamente. Las cédulas y los correos tienen códigos propios; no se presume su vínculo con una persona.
5. Revisa el texto completo de la comparación y pulsa **Crear copia anonimizada**. Se guardan exactamente los bytes preparados. Los originales se conservan. Se emplean nombres neutrales en las copias.
6. Carga al skill únicamente los DOCX anonimizados. La carpeta de salida contiene `LEER_ANTES_DE_CARGAR_AL_SKILL.txt` con la instrucción de conservar literalmente los códigos al redactar el proyecto de fallo. El SKILL.md local incorpora esa regla; una copia del skill ya cargada en ChatGPT debe actualizarse allí o recibir expresamente esa instrucción.
7. Descarga el proyecto de fallo en **DOCX**, **TXT** o **MD**. En la aplicación abre el caso correspondiente y pulsa **Restaurar fallo**. Elige el proyecto y una ruta nueva. Se reemplazan los códigos conocidos por sus valores originales sin modificar el proyecto de entrada. Se rechazan códigos de otro caso, marcadores modificados reconocibles y documentos sin códigos. Revisa el resultado antes de utilizarlo.

## Tabla privada

Los archivos ya anonimizados mantienen bloqueada la anonimización habitual. Si necesitas ocultar datos adicionales, selecciona el original y pulsa **Volver a anonimizar**. Se habilita una nueva revisión y selección de campos; al guardar se actualiza la misma copia anonimizada, con su nombre y ubicación actuales, sin acumular otra copia. El original se conserva. Si falla la sustitución, se conservan la copia anterior y su registro. Tras guardar, el archivo vuelve a quedar bloqueado hasta solicitar otra revisión.

Al abrir un caso local se recupera su lista de archivos. Delante de cada uno aparece **Anonimizado** o **No anonimizado**. El estado se actualiza al guardar la copia y comprueba que el original y una copia registrada mantengan su contenido. Preparar la vista previa no marca el archivo como anonimizado. Si cambia el original o deja de estar disponible la copia, aparece como No anonimizado. En casos antiguos se recupera el vínculo comparando localmente el texto restaurado de las copias con el original, sin volver a anonimizarlo. Este estado indica que se guardó una copia con los campos elegidos; revisa su contenido antes de compartirla.

Se guarda automáticamente en `%LOCALAPPDATA%\Anonimizador\casos\<identificador>.json`, separada de la carpeta de copias para cargar. **Ver tabla local** muestra dentro de la aplicación los códigos y sus datos originales en una tabla de solo lectura. Su selector permite consultar cualquier caso guardado e indica cuántas equivalencias tiene, sin cambiar el caso de trabajo. La aplicación muestra el nombre del caso; el identificador se administra internamente y se conserva dentro de los códigos. El nombre y la fecha se guardan únicamente en la tabla local. Los casos antiguos aparecen como «Caso sin nombre», con la fecha de modificación de su tabla.

La tabla JSON contiene datos personales en texto claro: no la subas al skill ni la compartas con las copias. Consérvala y respáldala en almacenamiento local autorizado; sin ella no se recuperan los valores. **Abrir caso local** permite retomarla después de cerrar la aplicación. Crear otro caso no borra tablas anteriores.

## Formatos y límites

Entradas: PDF, DOCX, XLSX, PPTX, JPG/JPEG/PNG/BMP/WebP/TIFF de una página y los formatos de texto compatibles del selector. Los DOC/XLS/PPT antiguos se admiten mediante conversión temporal local con Microsoft Word, Excel y PowerPoint instalados y pywin32 (incluido en requirements.txt). Los originales se abren en modo de solo lectura y las macros se deshabilitan en la instancia de conversión. Las copias para el skill siguen siendo DOCX. No se admiten ZIP, audio, vídeo, archivos protegidos con contraseña ni imágenes de varias páginas.

Las copias reversibles se reconstruyen como texto en Word; no conservan diseño, imágenes, tablas como tablas, objetos, comentarios ni revisiones. En PDF se extraen el texto y el OCR: pueden aparecer repeticiones o cambios del orden de lectura. En escaneos y fotografías el OCR puede omitir o confundir información. Los campos sin seleccionar permanecen visibles. Cero coincidencias no garantiza anonimización.

El fallo restaurado en DOCX también se reconstruye como texto: incluye párrafos, texto de tablas, cuadros de texto, encabezados y pies, pero pierde su diseño y formato. La restauración no recupera imágenes ni texto que el OCR haya omitido. Los códigos que el skill omita no permiten reconstruir información ausente; los datos nuevos que escriba sin código requieren revisión manual.

Las copias antiguas con `[ANONIMIZADO]` o tachaduras no se vuelven reversibles. Hay que procesar de nuevo los originales con códigos.

## Validación

Desde `anonimizador/`: `py -3.13 -m unittest discover -v`. Las pruebas usan documentos sintéticos, una sesión gráfica Windows y Arial para OCR. Las pruebas de integración de DOC/XLS/PPT también requieren Word, Excel y PowerPoint instalados. `motor.py` conserva el procesamiento irreversible para sus consumidores existentes; el flujo de la aplicación usa las copias reversibles por caso.

En **Abrir caso local**, selecciona un caso y pulsa **Eliminar caso** para borrar su tabla privada, previa confirmación. También se eliminan las copias anonimizadas asociadas, indicando su cantidad en la confirmación. Los originales se conservan. Sin la tabla ya no podrás restaurar sus códigos. Si eliminas el caso activo, queda deseleccionado.

**Ver archivos guardados** permite seleccionar documentos de todos los formatos compatibles en la carpeta de salida y abrirlos con la aplicación configurada en Windows.

La tabla local incluye **Archivos donde aparece**, con las rutas de los originales cuyos datos seleccionados se registraron al preparar la anonimización. Un dato mantiene el mismo código en la demanda y sus anexos; se acumulan sus archivos sin duplicarlos. Los casos antiguos indican «Sin registro de archivo» hasta volver a preparar sus originales. Las rutas permanecen en la tabla privada, fuera de las copias anonimizadas.

Las nuevas copias se vinculan al caso mediante su ruta y huella de contenido. Al eliminar el caso se borran esas copias y, al final, su tabla. Si una copia registrada cambió o no puede borrarse, se conserva la tabla para revisar y reintentar. Las copias anteriores se reconocen en la carpeta de destino actual y en la carpeta predeterminada por su nombre neutral y los códigos conocidos del caso. Las copias antiguas movidas a otra carpeta o sin códigos no pueden vincularse automáticamente.


La pestaña **Leer fallo restaurado** permite abrir desde cualquier carpeta un documento PDF, DOCX, XLSX, PPTX, imagen o texto/datos compatible y consultar su texto completo en modo de solo lectura. Al restaurar un fallo, el resultado se muestra automáticamente en esta pestaña. El lector conserva el archivo original; para consultar su diseño y formato, ábrelo en Word.
