import unittest
from analisis import detectar_campos
from motor import reemplazar, nombre_personal_valido, nombres_personas
from vista_previa import plan_configuracion


class Seleccion(unittest.TestCase):
    def test_descarta_falsos_nombres_de_documentos(self):
        for valor in ('Constancia', 'Registrar', 'Retener', 'radiqué', 'Ministerio',
                      'MINISTERIO', 'Máster Universitario', 'Bogotá D.C.',
                      'E. S. D. Referencia', 'Ministerio de Educación Nacional', 'Correo Electrónico'):
            with self.subTest(valor=valor):
                self.assertFalse(nombre_personal_valido(valor))
        for valor in ('Juan Pérez', 'MARÍA GARCÍA LÓPEZ', 'Ana de la Cruz'):
            self.assertTrue(nombre_personal_valido(valor))
        texto = 'La señora María García López\nCelular: 3001234567. Ministerio de Educación Nacional. Constancia de estudio.'
        candidatos = [texto[a:b] for a, b in nombres_personas(texto)]
        self.assertTrue(candidatos)
        self.assertTrue(all('Celular' not in valor and 'Ministerio' not in valor and '\n' not in valor for valor in candidatos))

    def test_tres_tipos_sin_numeros_ni_formulas_juridicas(self):
        texto = ('Señor Juez Municipal. Acción de tutela. Juan Pérez, C.C. 1.024.567.890. '
                 'Ana García, cédula de ciudadanía número 12345678. '
                 'Correos: juan@example.com y ana@example.com. '
                 'Teléfono 3001234567. Fecha 09/11/2026. Radicado 202600123.')
        campos = detectar_campos(texto)
        self.assertEqual(len(campos), 3)
        nombres = campos['Nombres propios de personas (detección en español)']
        self.assertIn('Juan Pérez', nombres)
        self.assertIn('Ana García', nombres)
        self.assertNotIn('Acción', nombres)
        self.assertNotIn('Señor Juez Municipal', nombres)
        self.assertEqual(campos['Documentos con etiqueta CC, TI, CE o NIT'], ['1.024.567.890', '12345678'])
        self.assertEqual(campos['Correos electrónicos'], ['ana@example.com', 'juan@example.com'])

    def test_solo_valores_marcados_sin_reglas_globales(self):
        campos = {'Correos electrónicos': ['ana@example.com', 'juan@example.com']}
        config = {'campos': campos, 'seleccionados': [('Correos electrónicos', 'ana@example.com')]}
        categorias, terminos = plan_configuracion(config)
        self.assertEqual(categorias, [])
        salida, count = reemplazar('ana@example.com y juan@example.com; teléfono 3001234567', categorias, terminos)
        self.assertEqual(salida, '[ANONIMIZADO] y juan@example.com; teléfono 3001234567')
        self.assertEqual(count, 1)
        self.assertEqual(reemplazar('Ana y Mariana', [], ['Ana'])[0], '[ANONIMIZADO] y Mariana')


if __name__ == '__main__':
    unittest.main()
