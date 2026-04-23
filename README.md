# huente_app
Aplicacion para los Informes.

#Actualizar Github
git add .
git commit -m "Primer cambio desde VS Code"
git push origin main
git push --set-upstream origin prueba-cambios //Rama
git push origin main --force

Se modifico y necesita nuevos cambios

Rama Principal

git checkout main

Secundaria

git checkout feature/contacarvajal





# Crear CArpeta Local
En MAC es con python3
python -m venv venv

# y dependencias 
pip install -r requirements.txt


# Activar LocalHost

.\venv\Scripts\activate
mac.  source venv/bin/activate

#Primer Entorno
    pip install -r requirements.txt
    
# y ejecutar la app
python3 app.py

# Crear ZIP
git archive -o huente_app.zip HEAD

# Abrir mysql desde Mac
mysql -u root -p
show DATABASES;
