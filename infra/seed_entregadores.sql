-- Entregadores extras (PIN 1234). Idempotente: rodar de novo não duplica nada.
INSERT INTO funcionarios (matricula, nome, funcao, pin_hash, ativo, disponivel) VALUES
  ('2002', 'Diego',    'entregador', '$2b$12$uRsO5txT2MCgBYPts077C.8Pf4Nhqhb0zbwfQA6ScrZ7gRhdYrQda', true, true),
  ('2003', 'Fernanda', 'entregador', '$2b$12$uRsO5txT2MCgBYPts077C.8Pf4Nhqhb0zbwfQA6ScrZ7gRhdYrQda', true, true)
ON CONFLICT (matricula) DO NOTHING;
