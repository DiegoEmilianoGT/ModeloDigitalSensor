#pragma once

void iniciarRed();
// avanza la conexion sin detener el loop; devuelve true justo al conectarse (o reconectarse)
bool gestionarWiFi();
bool redConectada();
void avisarIPPeriodico();
