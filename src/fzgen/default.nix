{ buildPythonPackage, setuptools }:

buildPythonPackage {
  pname = "fzgen";
  version = "0.1.0";
  pyproject = true;
  src = ./.;
  build-system = [ setuptools ];
  pythonImportsCheck = [ "fzgen.sketch" ];
}
