# Actualizador independiente

Al ejecutar `Instalar_actualizador.bat`, se crea el acceso directo y se abre inmediatamente la ventana que descarga la actualización desde GitHub. La carpeta del programa elegida en esa ventana se recuerda para las siguientes actualizaciones.

Para entregarlo a un usuario, envíe el ZIP completo del repositorio. El usuario debe extraerlo y ejecutar `Actualizador\Instalar_actualizador.bat`. El instalador copia el actualizador y el logo a `%LOCALAPPDATA%\Anonimizador\Actualizador` y crea **Actualizar Anonimizador** en el escritorio de ese usuario.

Después, el usuario abre el acceso directo con Python 3 instalado y elige la carpeta que contiene `app.py` e `Iniciar.bat`. El programa descarga la rama `main` de `Telecampux/ANONIMIZADOR`, comprueba el paquete y muestra la ruta y el número de archivos que reemplazará. Solo después de su autorización copia los archivos enumerados en `archivos_programa.json`.

Los demás archivos de la carpeta elegida no se borran. En particular, se conservan los documentos, las copias de recuperación `.restauracion`, `salida`, `tessdata` y `.venv`. Los datos que estén fuera de la carpeta del programa tampoco se modifican. Si la copia falla, el actualizador intenta restaurar los archivos anteriores. Cierre el Anonimizador antes de actualizar. Después, ejecute `iniciar.bat` para instalar las dependencias que requiera la versión nueva.
