// fix_duplicates.js — cambia el correo del usuario 'yiyo' al nuevo correo
db.Usuarios.updateOne(
  { Username: "yiyo" },
  { $set: { Correo: "rodrigo.erlandsen@alumnos.uach.cl" } }
);

print("=== Usuarios después del fix ===");
db.Usuarios.find({}, { Username: 1, Correo: 1, _id: 0 }).forEach(u => print(JSON.stringify(u)));
