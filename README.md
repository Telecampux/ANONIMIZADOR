# Anonimizador reversible local

Aplicación de escritorio en español para Windows, con selección de varios archivos. No sube documentos a servicios externos. Necesita Python 3.11 o posterior e internet únicamente para instalar dependencias.

## Iniciar

Haga doble clic en **iniciar.bat**. La primera ejecución crea un entorno virtual e instala las dependencias. También puede ejecutar:

```powershell
python -m pip install -r requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar_ocr.ps1
python app.py
```

1. Seleccione **Anonimizar archivos** y agregue documentos.
2. Si hace falta, escriba nombres de personas o identificaciones adicionales, uno por línea. Se buscan sin distinguir mayúsculas; incluya variantes y nombres parciales que también deban ocultarse.
3. La detección automática propone únicamente nombres propios de personas e identificaciones. Reconoce nombres junto a etiquetas de persona y formulario, e identificaciones junto a sus etiquetas. No propone correos, teléfonos, direcciones ni IP. Son reglas heurísticas: revise los resultados.
4. Elija la carpeta de salida y pulse **Anonimizar**. El avance muestra únicamente los nombres e identificaciones procesados, agrupados por página. En esta etapa no se guardan resultados ni copias de recuperación.
5. La ventana de revisión muestra cada dato, su contexto y su ubicación. Los nombres de personas, nombres en formularios, profesionales e identificaciones detectados quedan marcados automáticamente, incluidos los nombres o identificaciones añadidos manualmente. En la pestaña visual los datos marcados se muestran tachados; desmarcarlos permite volver a verlos en la vista previa.
6. Revise los nombres e identificaciones marcados automáticamente y desmarque los que desea conservar. Puede autorizar una aparición y conservar otra igual.
7. Si falta un nombre o identificación ilegible, puede dibujar su zona en la pestaña visual y autorizarla en la revisión.
8. Pulse **Autorizar seleccionados y generar** para guardar. Cancelar la revisión no genera ningún archivo. Si no hay coincidencias, se muestra el texto reconocido y se puede autorizar explícitamente una copia sin coincidencias o el sustituto indicado en los avisos.
9. Revise el resultado antes de compartirlo. Cero coincidencias no significa que el archivo carezca de datos sensibles.

**Cancelar anonimización** permite detener el análisis, el OCR en curso o la generación. Se interrumpe el lote y se elimina la salida incompleta del archivo en curso; los originales permanecen intactos. Los archivos del lote que ya terminaron se conservan. Durante la revisión puede usar **Cancelar sin generar archivos**.

### Anexos e historias clínicas

El OCR combina la lectura de página completa con contraste mejorado, texto disperso y columnas. Se proponen únicamente nombres de personas e identificaciones, como `CC-12345678`, incluidos los nombres de profesionales etiquetados y nombres separados de sus etiquetas por un salto de línea. Las lecturas adicionales pueden tardar más y las propuestas deben revisarse.

La lectura adaptativa y la eliminación de ruido ayudan con autorizaciones y cédulas fotocopiadas. En PDF se identifican primero los nombres y números personales del documento y después se buscan sus repeticiones en los anexos, incluso con apellidos antes de nombres o pequeñas variaciones del OCR. Se reutiliza el OCR al generar; no se vuelve a reconocer el documento después de autorizar.

En **Ubicación visual (OCR)** puede ampliar la imagen con el control superior y desplazarse con las barras. Arrastre un rectángulo sobre datos que no se reconozcan, fotografías, firmas o huellas: se añadirá una propuesta **ZONA**. Márquela para autorizar que se oculte todo el rectángulo. Las páginas sin propuestas automáticas aparecen como **REVISAR PÁGINA** para poder inspeccionarlas y dibujar zonas. Cada zona se aplica únicamente en su página o imagen; el original permanece en la copia de recuperación. Volver a analizar descarta las zonas y autorizaciones de la revisión anterior.

Se generan un archivo con datos sustituidos y una **copia de recuperación `.restauracion` sin cifrar**. Los originales permanecen intactos. En PDF se eliminan las áreas de texto detectadas y se muestran bloques negros; en los otros formatos se usan identificadores `ANON_…`.

## Desanonimizar

La interfaz ofrece dos opciones: **Anonimizar archivos** y **Restaurar archivos anonimizados**. Para restaurar los campos, cargue el fallo del sustanciador y la recuperación de los insumos del caso. Se conserva la redacción del fallo y se sustituyen automáticamente sus campos anonimizados por los datos originales.

Conserve la copia `.restauracion`: contiene el original y los campos guardados sin cifrar. Comparta únicamente el documento anonimizado. Sin la copia de recuperación no se pueden recuperar los datos eliminados.

### Cargar los datos originales en un fallo nuevo

Las nuevas copias `.restauracion` guardan también la correspondencia entre cada código `ANON_…` autorizado y su dato original. El restaurador detecta los códigos que ya aparecen en el fallo y carga automáticamente los datos originales sin perder la decisión ni el texto nuevo del sustanciador. No necesita copiar ni marcar los campos uno por uno.

1. Seleccione **Restaurar archivos anonimizados**, pulse **Cargar archivo…** y elija el fallo elaborado por el sustanciador. Su ruta aparece en el panel; los insumos seleccionados para anonimizar se mantienen separados.
2. Pulse **Cargar tabla o insumo anonimizado…** y seleccione la tabla `.restauracion` o el documento anonimizado que tiene esa tabla a su lado. Se muestran el nombre y la ruta del fallo, el nombre y la ruta de la tabla y el insumo anonimizado asociado. Si la tabla acompaña al fallo seleccionado, se carga automáticamente.
3. Pulse **Restaurar campos automáticamente**. Se sustituyen todas las apariciones de los códigos conocidos y se crea una nueva copia `fallo_restaurado_…`, conservando el archivo de entrada.

Los códigos y sus datos originales aparecen directamente en la pantalla de restauración. **Ver tabla completa** abre una consulta ampliada; no es necesario abrirla para restaurar el fallo. Los controles para añadir datos sensibles y activar detección se muestran solo al anonimizar. Al cargar otro fallo o intentar cargar una tabla inválida se limpia la recuperación anterior.

Los códigos nuevos incluyen un identificador propio del análisis, para que dos documentos con un primer nombre anonimizado no compartan el mismo código. Si aparece un código que no está en la recuperación seleccionada, se informa el problema y no se genera una copia incompleta. Las tablas anteriores siguen siendo compatibles; sus códigos genéricos no identifican por sí solos el caso y requieren elegir su recuperación correcta.

Se admiten Word `.docx`, texto `.txt`, `.md`, `.log`, `.rst` y PDF con los códigos como texto seleccionable. En Word se conservan imágenes, estilos y las partes no modificadas; se reconocen códigos divididos entre fragmentos de formato, encabezados y pies. En PDF el dato se ajusta al espacio del código: si no cabe con letra legible, se solicita usar Word. Un escaneo o un bloque negro no es un código editable.

Las recuperaciones antiguas siguen restaurando el original completo, pero no contienen esta tabla de campos. Para usarla, restaure el original y vuelva a anonimizarlo con esta versión. Las zonas dibujadas no generan códigos de texto porque pueden contener fotos, firmas o información ilegible.

## Archivos de cualquier extensión

Solo se descartan audios y videos, también cuando están dentro de un ZIP. La extensión no determina si un archivo se acepta: se inspecciona su contenido.

| Contenido detectado | Tratamiento |
|---|---|
| Texto con cualquier extensión | Sustitución de datos; JSON y XML conservan su estructura cuando son válidos |
| Office / OpenDocument | Sustitución de texto y OCR selectivo en imágenes incrustadas; limpieza de metadatos principales |
| PDF | Redacción de texto; OCR local a 300 DPI en páginas escaneadas o con imágenes; se omiten adjuntos |
| Imágenes | OCR local en español e inglés: se tachan las palabras sensibles y se conserva el resto de la imagen; se eliminan metadatos |
| ZIP | Se procesan sus archivos recursivamente, se descarta audio/video y se renombra cada entrada |
| Otros binarios, documentos protegidos, dañados o contenido que no se pueda interpretar | Se genera un PDF sustituto con el contenido completamente omitido y un aviso en el registro |

Aceptar cualquier extensión no significa conservar el contenido visible de todos los formatos. En formatos que no se pueden interpretar, el PDF sustituto **no es una conversión del documento**: omite todo el contenido. Se informa expresamente en el registro. El original se conserva íntegro en la copia `.restauracion`, también en estos casos. En imágenes y escaneos se reconocen palabras con Tesseract y se tachan las áreas que coinciden con los nombres o identificaciones manuales y los patrones automáticos. Los nombres manuales pueden abarcar varios renglones. Las sugerencias de nombres de personas se basan en etiquetas, no en reconocimiento general de entidades.

Los documentos con macros u objetos binarios incrustados también generan un PDF sustituto. Los PDF con contraseña se procesan de esta manera sin pedir contraseña. Los archivos de salida tienen nombres genéricos para evitar que el nombre original revele datos. La restauración recupera el nombre base y la extensión original.

Límite de entrada: 100 MB por archivo; contenido ZIP/Office descomprimido: 300 MB y hasta ocho niveles de ZIP anidados. Son límites operativos, no exclusiones de formatos. Los archivos que superan el límite de entrada generan un error explícito. Se procesa un archivo a la vez y los errores no detienen el lote.

Revise los resultados y los avisos del registro. Los documentos complejos pueden cambiar de formato, perder firmas digitales, enlaces o propiedades. Las reglas pueden omitir datos que no coincidan con los patrones ni la lista manual. Esta herramienta no certifica que un documento esté libre de información identificable.

## OCR local instalado

El OCR usa Tesseract con los modelos oficiales `spa` y `eng` en la carpeta `tessdata`. Las imágenes se procesan localmente; no se envían a un servicio externo. El instalador descarga el motor y los modelos una vez. `iniciar.bat` comprueba la instalación.

En PDF escaneados o mixtos se procesa la apariencia de cada página a 300 DPI. La salida conserva su tamaño visible y contiene únicamente la imagen ya tachada, sin el escaneo original ni una capa oculta de texto. Esas páginas dejan de tener texto seleccionable. En imágenes multipágina se procesa cada fotograma/página. Las páginas de PDF con texto nativo conservan la redacción de texto habitual.

El registro muestra cuántas imágenes/páginas recibieron OCR y avisa si hay palabras de baja confianza o no se reconoce texto. El reconocimiento puede fallar con documentos borrosos, girados, manuscritos o diseños complejos: revise siempre las propuestas y el resultado. Si el motor falla o falta, el procesamiento informa un error y no genera un documento marcado como anonimizado.

Documentación del motor: [Tesseract: uso de la línea de comandos y salida TSV](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).

## Consola

```powershell
python anonimizador.py anonimizar documento.docx --datos sensibles.txt --salida salida
python anonimizador.py restaurar salida\documento_anon_XXXXXXXX.docx --salida recuperados
python -m unittest -v
```

La consola también muestra propuestas y pide los números que autoriza (o `TODAS`); Enter cancela sin guardar.

`sensibles.txt`: UTF-8 con un dato por línea. Use `--solo-manual` para desactivar las reglas automáticas.


Carpetas de trabajo: `C:\TUTELAS\ORIGINALES` contiene los archivos originales. `C:\TUTELAS\ANONIMIZADOS` contiene los archivos anonimizados, sus copias de recuperación y los archivos restaurados.
