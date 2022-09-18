import ts from "typescript";

type CodeBlockTree = {
  name: string;
  code: string;
  children: CodeBlockTree[];
};

export const makeTree = (sourceFile: ts.SourceFile): CodeBlockTree[] => {
  // create the printer, TODO: make into a singleton
  const printer = ts.createPrinter({
    newLine: ts.NewLineKind.LineFeed,
    removeComments: false,
    omitTrailingSemicolon: false,
  });

  const traverse = (
    child: ts.Node,
    ctxName: string,
    ctxNode: CodeBlockTree | undefined
  ): CodeBlockTree => {
    const code = printer.printNode(ts.EmitHint.Unspecified, child, sourceFile);

    // only make children out of function declarations
    if (child.kind === ts.SyntaxKind.FunctionDeclaration) {
      const func = child as ts.FunctionDeclaration;
      const name = func.name?.escapedText.toString() ?? "anonymous"; // TODO: handle this case, we don't want to do anon
      console.log("func name: ", name);

      let thisNode = { name, code, children: [] };

      func.body?.statements.forEach((child) => traverse(child, name, thisNode));

      if (ctxNode) {
        ctxNode.children.push(thisNode);
      }

      return thisNode;
    }

    if (ctxNode === undefined) {
      let thisNode = { name: ctxName, code, children: [] };
      child.forEachChild((child) => {
        traverse(child, ctxName, thisNode);
      });
      return thisNode;
    }

    child.forEachChild((child) => {
      traverse(child, ctxName, ctxNode);
    });

    return ctxNode;
  };

  let forest: CodeBlockTree[] = [];

  ts.forEachChild(sourceFile, (child) => {
    forest.push(traverse(child, "ctx", undefined)); // TODO: undefined?
  });
  
  // filter nodes with code === ""
  forest = forest.filter((node) => node.code !== "");

  return forest;
};
