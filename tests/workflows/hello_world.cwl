cwlVersion: v1.0
class: Workflow

requirements:
  DockerRequirement:
    dockerPull: ubuntu:latest

inputs: []

steps:
  say_hello:
    run:
      class: CommandLineTool
      baseCommand: [echo, "Hello, World!"]
      stdout: hello.txt
      inputs: []
      outputs:
        output_file:
          type: stdout
    in: []
    out: [output_file]

outputs:
  output_file:
    type: File
    outputSource: say_hello/output_file
